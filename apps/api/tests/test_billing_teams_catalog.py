"""Subscriptions + credit packs (token-based usage), teams (roles, invites, projects, comments, reviews, pooled
credits) and the research catalog API. Everything runs offline against SQLite."""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from app.api.deps import AuthContext, get_auth_context
from app.core.config import settings
from app.services.billing import service as billing
from app.services.billing.providers import SandboxProvider, StripeProvider, WebhookError, LemonSqueezyProvider, PaddleProvider
from app.services.credits import service as credits


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "database_url", f"sqlite:///{tmp_path / 'app.sqlite3'}")
    monkeypatch.setattr(settings, "deployment_stage", "development")
    ledger = credits.CreditService(str(tmp_path / "credits.sqlite3"))
    monkeypatch.setattr(credits, "_default_service", ledger)
    monkeypatch.setenv("BILLING_PROVIDER", "sandbox")
    monkeypatch.setenv("CATALOG_DATABASE_URL", f"sqlite:///{tmp_path / 'catalog.sqlite3'}")
    monkeypatch.setenv("PIPELINE_OUTPUT_DIR", str(tmp_path / "pipeline"))
    from app.api.v1.endpoints import billing as billing_router
    from app.api.v1.endpoints import catalog as catalog_router
    from app.api.v1.endpoints import teams as teams_router
    import app.services.catalog.service as catalog_service

    monkeypatch.setattr(catalog_service, "_service", None)
    app = FastAPI()
    app.include_router(billing_router.router, prefix="/billing")
    app.include_router(teams_router.router, prefix="/teams")
    app.include_router(catalog_router.router, prefix="/catalog")

    def auth(request: Request) -> AuthContext:
        return AuthContext(user_id=request.headers.get("x-test-user", "alice"), source="test", verified=True)

    app.dependency_overrides[get_auth_context] = auth
    billing.install()
    yield TestClient(app), ledger
    credits.set_plan_resolver(None)
    credits.set_topup_hooks(None)


def as_user(user: str) -> dict[str, str]:
    return {"x-test-user": user}


def buy(client, user, **body):
    response = client.post("/billing/checkout", json=body, headers=as_user(user))
    assert response.status_code == 200, response.text
    session = response.json()
    assert session["url"] == f"/billing/checkout/{session['session_id']}"
    done = client.post(f"/billing/sandbox/{session['session_id']}/complete", headers=as_user(user))
    assert done.status_code == 200 and done.json()["status"] == "completed", done.text
    return session


# ---------------------------------------------------------------- plans + subscriptions

def test_plans_catalog_matches_enforced_limits(env):
    client, _ = env
    data = client.get("/billing/plans").json()
    plans = {plan["id"]: plan for plan in data["plans"]}
    assert plans["pro"]["limits"] == credits.CreditService.limits("pro")
    assert plans["team"]["per_seat"] and plans["team"]["min_seats"] == 3
    assert data["sandbox"] is True and {pack["id"] for pack in data["packs"]} == {"credits_100", "credits_500", "credits_2000"}


def test_subscribe_trial_then_renew_upgrade_and_cancel(env):
    client, ledger = env
    me = client.get("/billing/me", headers=as_user("alice")).json()
    assert me["plan"] == "free" and me["subscription"] is None
    buy(client, "alice", kind="subscription", plan="pro", interval="month", currency="pkr")
    me = client.get("/billing/me", headers=as_user("alice")).json()
    assert me["plan"] == "pro" and me["subscription"]["status"] == "trialing"  # 7-day trial, no invoice yet
    assert client.get("/billing/invoices", headers=as_user("alice")).json()["invoices"] == []
    # plan limits apply to the credit windows of signed-in users
    usage = ledger.usage("user:alice", "free")
    assert usage["plan"] == "pro" and usage["windows"][0]["limit"] == credits.CreditService.limits("pro")["session"]

    # time passes: the trial ends and the first paid period starts (lazy renewal, sandbox provider)
    with billing._db() as db:
        db.run("update billing_subscriptions set current_period_end = ? where owner_id = 'alice'", ("2020-01-01T00:00:00+00:00",))
    sub = client.get("/billing/me", headers=as_user("alice")).json()["subscription"]
    assert sub["status"] == "active"
    invoices = client.get("/billing/invoices", headers=as_user("alice")).json()["invoices"]
    assert invoices and all(inv["currency"] == "pkr" for inv in invoices) and invoices[0]["kind"] == "renewal"
    doc = client.get(f"/billing/invoices/{invoices[0]['id']}/document", headers=as_user("alice"))
    assert doc.status_code == 200 and "Invoice RS-" in doc.text and "Rs " in doc.text

    # downgrade to free is scheduled for the period end; cancel/resume toggles cancel_at_period_end
    change = client.post("/billing/subscription/change", json={"plan": "free", "interval": "month"}, headers=as_user("alice")).json()
    assert change["applied"] == "period_end"
    cancel = client.post("/billing/subscription/cancel", headers=as_user("alice")).json()
    assert cancel["cancel_at_period_end"] == 1
    resumed = client.post("/billing/subscription/resume", headers=as_user("alice")).json()
    assert resumed["cancel_at_period_end"] == 0
    client.post("/billing/subscription/cancel", headers=as_user("alice"))
    with billing._db() as db:
        db.run("update billing_subscriptions set current_period_end = ? where owner_id = 'alice'", ("2020-01-01T00:00:00+00:00",))
    assert client.get("/billing/me", headers=as_user("alice")).json()["plan"] == "free"


def test_checkout_rules_and_sandbox_security(env, monkeypatch):
    client, _ = env
    assert client.post("/billing/checkout", json={"kind": "subscription", "plan": "institution"}, headers=as_user("bob")).json()["detail"]["code"] == "plan_not_purchasable"
    assert client.post("/billing/checkout", json={"kind": "subscription", "plan": "team"}, headers=as_user("bob")).json()["detail"]["code"] == "team_required"
    session = client.post("/billing/checkout", json={"kind": "topup", "pack": "credits_100"}, headers=as_user("bob")).json()
    # another person cannot see or complete bob's checkout
    assert client.get(f"/billing/checkout/{session['session_id']}", headers=as_user("eve")).status_code == 404
    assert client.post(f"/billing/sandbox/{session['session_id']}/complete", headers=as_user("eve")).status_code == 404
    monkeypatch.setattr(settings, "deployment_stage", "production")
    assert client.post(f"/billing/sandbox/{session['session_id']}/complete", headers=as_user("bob")).status_code in (401, 403)


def test_webhooks_are_verified_and_idempotent(env):
    client, _ = env
    body = json.dumps({"id": "evt_x", "type": "checkout.completed", "data": {"session_id": "missing"}}).encode()
    bad = client.post("/billing/webhooks/sandbox", content=body, headers={"x-resora-signature": "t=1,v1=00"})
    assert bad.status_code == 400
    good = {"x-resora-signature": SandboxProvider.sign(body)}
    assert client.post("/billing/webhooks/sandbox", content=body, headers=good).json()["applied"] == 1
    assert client.post("/billing/webhooks/sandbox", content=body, headers={"x-resora-signature": SandboxProvider.sign(body)}).json()["applied"] == 0


def test_provider_signature_schemes(monkeypatch):
    import hashlib
    import hmac

    monkeypatch.setenv("BILLING_WEBHOOK_SECRET", "whsec_test")
    stamp = int(time.time())
    stripe_body = json.dumps({"id": "evt_1", "type": "checkout.session.completed", "data": {"object": {"client_reference_id": "cs_1", "subscription": "sub_1", "customer": "cus_1"}}}).encode()
    sig = hmac.new(b"whsec_test", f"{stamp}.".encode() + stripe_body, hashlib.sha256).hexdigest()
    events = StripeProvider().verify_and_parse({"stripe-signature": f"t={stamp},v1={sig}"}, stripe_body)
    assert events[0].type == "checkout.completed" and events[0].data["session_id"] == "cs_1"
    with pytest.raises(WebhookError):
        StripeProvider().verify_and_parse({"stripe-signature": f"t={stamp - 4000},v1={sig}"}, stripe_body)  # replayed
    paddle_body = json.dumps({"event_id": "e1", "event_type": "subscription.canceled", "data": {"id": "sub_9"}}).encode()
    psig = hmac.new(b"whsec_test", f"{stamp}:".encode() + paddle_body, hashlib.sha256).hexdigest()
    assert PaddleProvider().verify_and_parse({"paddle-signature": f"ts={stamp};h1={psig}"}, paddle_body)[0].type == "subscription.canceled"
    lemon_body = json.dumps({"meta": {"event_name": "subscription_payment_failed"}, "data": {"id": "7", "attributes": {"subscription_id": 7}}}).encode()
    lsig = hmac.new(b"whsec_test", lemon_body, hashlib.sha256).hexdigest()
    assert LemonSqueezyProvider().verify_and_parse({"x-signature": lsig}, lemon_body)[0].type == "subscription.past_due"


def test_credit_packs_are_used_only_after_windows_and_refunded(env, monkeypatch):
    client, ledger = env
    monkeypatch.setenv("CREDIT_PLAN_LIMITS", json.dumps({"free": {"session": 2, "week": 100, "month": 100}}))
    buy(client, "carol", kind="topup", pack="credits_100", currency="usd")
    assert client.get("/billing/me", headers=as_user("carol")).json()["topup_balance"] == 100
    first = ledger.reserve("user:carol", "summary")  # 2 credits fit the 5-hour window
    ledger.commit(first)
    assert billing.topup_balance("carol") == 100
    second = ledger.reserve("user:carol", "summary")  # window full → paid from the pack
    assert billing.topup_balance("carol") == 98
    ledger.refund(second)  # failed action → credits go back to the pack
    assert billing.topup_balance("carol") == 100
    third = ledger.reserve("user:carol", "summary")
    ledger.commit(third, 1)  # cheaper than reserved → difference returned
    assert billing.topup_balance("carol") == 99
    invoices = client.get("/billing/invoices", headers=as_user("carol")).json()["invoices"]
    assert invoices[0]["kind"] == "topup" and invoices[0]["amount"] == 300
    with pytest.raises(credits.CreditLimitReached):
        ledger.reserve("user:dave", "summary", amount=5)  # no pack → limit message as before


# ---------------------------------------------------------------- teams

def make_team(client):
    team = client.post("/teams", json={"name": "Thesis lab", "display_name": "Alice"}, headers=as_user("alice")).json()
    invite = client.post(f"/teams/{team['id']}/invites", json={"role": "supervisor", "max_uses": 1}, headers=as_user("alice")).json()
    assert client.get(f"/teams/invites/{invite['token']}").json()["team"]["name"] == "Thesis lab"
    assert client.post(f"/teams/invites/{invite['token']}/accept", json={"display_name": "Prof Khan"}, headers=as_user("khan")).json()["already_member"] is False
    assert client.post(f"/teams/invites/{invite['token']}/accept", json={"display_name": "Eve"}, headers=as_user("eve")).status_code == 410  # single use
    member = client.post(f"/teams/{team['id']}/invites", json={"role": "member"}, headers=as_user("alice")).json()
    client.post(f"/teams/invites/{member['token']}/accept", json={"display_name": "Bilal"}, headers=as_user("bilal"))
    return team["id"]


def test_team_roles_invites_and_isolation(env):
    client, _ = env
    team_id = make_team(client)
    detail = client.get(f"/teams/{team_id}", headers=as_user("khan")).json()
    assert detail["my_role"] == "supervisor" and [m["role"] for m in detail["members"]] == ["owner", "supervisor", "member"]
    assert client.get(f"/teams/{team_id}", headers=as_user("eve")).status_code == 404  # outsiders see nothing
    assert client.post(f"/teams/{team_id}/invites", json={"role": "member"}, headers=as_user("bilal")).status_code == 403
    assert client.patch(f"/teams/{team_id}/members/khan", json={"role": "admin"}, headers=as_user("bilal")).status_code == 403
    assert client.delete(f"/teams/{team_id}/members/alice", headers=as_user("alice")).json()["detail"]["code"] == "owner_cannot_leave"
    invites = client.get(f"/teams/{team_id}/invites", headers=as_user("alice")).json()["invites"]
    assert all("token" not in invite and "token_hash" not in invite for invite in invites)
    assert client.get("/teams/notifications/me", headers=as_user("alice")).json()["notifications"][0]["kind"] == "member_joined"
    activity = client.get(f"/teams/{team_id}/activity", headers=as_user("bilal")).json()["activity"]
    assert {row["action"] for row in activity} >= {"team.created", "invite.created", "member.joined"}


def test_shared_projects_comments_mentions_and_reviews(env, monkeypatch):
    client, _ = env
    team_id = make_team(client)
    project = client.post(f"/teams/{team_id}/projects", json={"name": "Chapter 2"}, headers=as_user("alice")).json()
    paper = {"title": "Attention is all you need", "authors": ["A. Vaswani"], "year": 2017, "doi": "10.48550/arXiv.1706.03762"}
    added = client.post(f"/teams/{team_id}/projects/{project['id']}/papers", json={"papers": [paper, paper]}, headers=as_user("bilal")).json()
    assert added["added"] == 1  # the duplicate inside one request is skipped by paper key
    again = client.post(f"/teams/{team_id}/projects/{project['id']}/papers", json={"papers": [paper]}, headers=as_user("bilal")).json()
    assert again["added"] == 0 and again["skipped"] == 1  # shared lists never duplicate a paper
    paper_id = again["project"]["papers"][0]["id"]
    updated = client.patch(f"/teams/{team_id}/projects/{project['id']}/papers/{paper_id}", json={"status": "reading", "assignee_id": "khan"}, headers=as_user("bilal")).json()
    assert updated["papers"][0]["status"] == "reading" and updated["papers"][0]["assignee_id"] == "khan"

    comment = client.post(f"/teams/{team_id}/comments", json={"target_type": "paper", "target_id": paper_id, "body": "@Prof Khan is this the right baseline?"}, headers=as_user("bilal")).json()
    assert comment["mentions"] == ["khan"] and comment["author_name"] == "Bilal"
    kinds = [n["kind"] for n in client.get("/teams/notifications/me", headers=as_user("khan")).json()["notifications"]]
    assert "mention" in kinds and "paper_assigned" in kinds
    reply = client.post(f"/teams/{team_id}/comments", json={"target_type": "paper", "target_id": paper_id, "body": "Yes", "parent_id": comment["id"]}, headers=as_user("khan")).json()
    assert reply["parent_id"] == comment["id"]
    assert client.patch(f"/teams/{team_id}/comments/{comment['id']}", json={"body": "edit"}, headers=as_user("khan")).status_code == 403

    # supervisor review of a Write document
    from app.services.write.store import WriteStore

    store_w = WriteStore()
    doc = store_w.create_document("bilal", {"kind": "draft", "title": "Introduction", "style": "introduction", "language": "en", "citation_style": "apa", "sources": [], "sections": []})
    doc = store_w.update_document("bilal", doc["id"], {"content": {"sections": [{"id": "s1", "heading": "Intro", "purpose": "introduction", "papers": [], "text": "Transformers changed NLP.", "status": "edited", "unsupported": []}]}})
    review = client.post(f"/teams/{team_id}/reviews", json={"document_id": doc["id"]}, headers=as_user("bilal"))
    assert review.status_code == 201, review.text
    review = review.json()
    assert "Transformers changed NLP." in review["snapshot"] and review["can_decide"] is False
    assert client.post(f"/teams/{team_id}/reviews/{review['id']}/decision", json={"status": "approved"}, headers=as_user("bilal")).status_code == 403
    decided = client.post(f"/teams/{team_id}/reviews/{review['id']}/decision", json={"status": "changes_requested", "note": "Cite sources"}, headers=as_user("khan")).json()
    assert decided["status"] == "changes_requested" and decided["decision_note"] == "Cite sources"
    assert any(n["kind"] == "review_decided" for n in client.get("/teams/notifications/me", headers=as_user("bilal")).json()["notifications"])
    assert client.post(f"/teams/{team_id}/reviews", json={"document_id": doc["id"]}, headers=as_user("khan")).status_code == 404  # not khan's document


def test_team_plan_pools_credits_across_members(env):
    client, ledger = env
    team_id = make_team(client)
    buy(client, "alice", kind="subscription", plan="team", interval="month", currency="usd", seats=3, team_id=team_id)
    assert client.get(f"/teams/{team_id}", headers=as_user("bilal")).json()["subscription"]["plan"] == "team"
    usage = ledger.usage("user:bilal", "free")
    assert usage["plan"] == "team" and usage["pooled"] and usage["windows"][0]["limit"] == credits.CreditService.limits("team")["session"] * 3
    rid = ledger.reserve("user:bilal", "summary")
    ledger.commit(rid)
    assert ledger.usage("user:khan", "free")["windows"][0]["used"] == 2  # same pool
    team_usage = client.get(f"/teams/{team_id}/usage", headers=as_user("khan")).json()
    assert team_usage["pooled"] and team_usage["seats"] == 3 and team_usage["usage"]["windows"][0]["used"] == 2
    assert client.post("/billing/checkout", json={"kind": "subscription", "plan": "team", "seats": 3, "team_id": team_id}, headers=as_user("bilal")).status_code == 403


# ---------------------------------------------------------------- research catalog (pipeline output)

def test_catalog_api_reads_pipeline_output(env, tmp_path):
    client, _ = env
    import importlib.util

    spec = importlib.util.spec_from_file_location("pipeline_fixtures", Path(__file__).resolve().parents[2] / "pipeline" / "tests" / "conftest.py")
    fixtures = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(fixtures)
    make_corpus, write_corpus = fixtures.make_corpus, fixtures.write_corpus
    from resora_pipeline.config import PipelineConfig
    from resora_pipeline.lake import DataLake, LocalStorage
    from resora_pipeline.orchestrator import Pipeline

    config = PipelineConfig(lake_uri=(tmp_path / "lake").as_uri(), catalog_database_url=f"sqlite:///{tmp_path / 'catalog.sqlite3'}", output_dir=tmp_path / "pipeline")
    lake = DataLake(LocalStorage(tmp_path / "lake"))
    corpus = make_corpus()
    write_corpus(lake, corpus)
    Pipeline(config, lake=lake).run(queries=[], sources=[], skip_ingest=True, run_id="api-run")

    overview = client.get("/catalog/overview").json()
    assert overview["papers"] == len(corpus) and overview["duplicates_merged"] > 0 and overview["index"]["papers"] == len(corpus)
    analytics = client.get("/catalog/analytics").json()
    assert analytics["publication_trends"] and analytics["topic_trends"]
    hits = client.get("/catalog/search", params={"q": "knowledge distillation speech recognition", "limit": 5}).json()
    assert hits["index_ready"] and "knowledge distillation" in hits["results"][0]["title"].lower()
    assert set(hits["results"][0]["match"]["matched"]) <= {"keyword", "semantic"}
    one = client.get(f"/catalog/papers/{hits['results'][0]['paper_id']}").json()
    assert one["source_records"]
    assert client.get("/catalog/runs").json()["runs"][0]["run_id"] == "api-run"
    assert client.post("/catalog/runs", json={"queries": ["x"], "sources": ["nope"]}).status_code == 422
