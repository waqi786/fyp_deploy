"""Admin console (role, metrics, users, credit grants, suspension, flags, dead letters, incidents, audit), Listen
(clean listening script, voice registry, neural speech with credits per chunk, resume, queue) and the public site
(status, newsletter double opt-in, contact, cookieless analytics, referral credits). Offline, SQLite, fake TTS."""

from __future__ import annotations

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from app.api.deps import AuthContext, get_auth_context
from app.core.config import settings
from app.services.admin import service as admin
from app.services.billing import service as billing
from app.services.credits import service as credits
from app.services.listen import tts
from app.services.listen.script import ScriptOptions, build_script, script_from_texts, split_sentences


class FakeEngine(tts.KokoroEngine):
    def __init__(self) -> None:
        super().__init__(base_url="http://fake-tts")
        self.calls: list[str] = []
        self.fail = False

    def synthesize(self, text: str, voice: str, speed: float = 1.0):
        if self.fail:
            raise tts.TTSUnavailable("engine_error")
        self.calls.append(text)
        return (b"ID3" + text.encode()[:20], "audio/mpeg")


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "database_url", f"sqlite:///{tmp_path / 'app.sqlite3'}")
    monkeypatch.setattr(settings, "deployment_stage", "development")
    ledger = credits.CreditService(str(tmp_path / "credits.sqlite3"))
    monkeypatch.setattr(credits, "_default_service", ledger)
    monkeypatch.setenv("ADMIN_USER_IDS", "root")
    monkeypatch.setenv("BILLING_PROVIDER", "sandbox")
    monkeypatch.setattr(admin, "_suspended_cache", {})
    engine = FakeEngine()
    tts.set_tts_router(tts.TTSRouter(engines=[engine], cache_dir=tmp_path / "tts"))
    from app.api.v1.endpoints import admin as admin_router
    from app.api.v1.endpoints import billing as billing_router
    from app.api.v1.endpoints import growth as growth_router
    from app.api.v1.endpoints import listen as listen_router
    from app.api.v1.router import block_suspended
    from fastapi import APIRouter, Depends

    app = FastAPI()
    guarded = APIRouter(dependencies=[Depends(block_suspended)])
    guarded.include_router(admin_router.router, prefix="/admin")
    guarded.include_router(listen_router.router, prefix="/listen")
    guarded.include_router(growth_router.router, prefix="/site")
    guarded.include_router(billing_router.router, prefix="/billing")
    app.include_router(guarded)

    def auth(request: Request) -> AuthContext:
        user = request.headers.get("x-test-user", "alice")
        return AuthContext(user_id=user, source="test", verified=user != "anonymous")

    app.dependency_overrides[get_auth_context] = auth
    billing.install()
    growth_router._HITS.clear()
    yield TestClient(app), engine, ledger
    tts.set_tts_router(None)
    credits.set_plan_resolver(None)
    credits.set_topup_hooks(None)


def as_user(user: str) -> dict[str, str]:
    return {"x-test-user": user}


PAPER = [
    "Deep Learning for Medical Imaging\nA. Author, B. Author\nJournal of Tests 2024\n1\n"
    "Abstract\nConvolutional networks (CNNs) achieve 95% accuracy [3], [5–7] on the bench-\nmark (Smith et al., 2020). "
    "See https://example.org/code and doi:10.1000/xyz.123 for details. Contact a@b.org.\n"
    "1 Introduction\nMedical imaging is hard. We study it with α = 0.5 and p < 0.05 e.g. on chest X-rays.\n",
    "Journal of Tests 2024\n2\nx = ∑ w_i · y_i + b ≤ ∞\nFigure 2: Accuracy per dataset. More words follow here.\n"
    "2 Results\nThe ﬁnal model is better. It runs at 30 ms per image.\nAcknowledgments\nWe thank our funders.\n",
    "Journal of Tests 2024\n3\nReferences\n[1] A. Author. Some paper. 2019.\n[2] B. Author. Other paper. 2020.\n",
]


def test_listening_script_skips_references_cleans_markers_and_expands_terms():
    script = build_script(PAPER, language="en", title="Deep Learning for Medical Imaging", authors=["A", "B", "C", "D"])
    text = " ".join(sentence for section in script["sections"] for sentence in section["sentences"])
    titles = [section["title"] for section in script["sections"]]
    assert "Abstract" in titles and "Introduction" in titles and "Results" in titles
    assert "References" not in titles and "Some paper" not in text and "We thank" not in text
    assert "[3]" not in text and "Smith et al." not in text and "https://" not in text and "10.1000" not in text and "a@b.org" not in text
    assert "benchmark" in text and "final model" in text  # hyphenation and ligature repaired
    assert "C N Ns" in text and "95 percent" in text and "alpha" in text and "p less than 0.05" in text and "for example" in text
    assert "30 milliseconds" in text and "Figure 2. Accuracy per dataset." in text and "Equation — see the paper." in text
    assert "Journal of Tests" not in text  # running header removed
    assert script["sections"][0]["sentences"][1] == "A, B, C and colleagues."
    assert script["characters"] > 100 and script["minutes"] > 0
    with_refs = build_script(PAPER, language="en", options=ScriptOptions(read_references=True))
    assert any(section["title"] == "References" for section in with_refs["sections"])


def test_sentence_segmentation_per_script_and_translated_note():
    assert split_sentences("یہ پہلا جملہ ہے۔ یہ دوسرا ہے؟ تیسرا!", "ur") == ["یہ پہلا جملہ ہے۔", "یہ دوسرا ہے؟", "تیسرا!"]
    assert split_sentences("这是第一句。这是第二句！第三句？", "zh-Hans") == ["这是第一句。", "这是第二句！", "第三句？"]
    assert split_sentences("यह पहला वाक्य है। यह दूसरा है।", "hi") == ["यह पहला वाक्य है।", "यह दूसरा है।"]
    assert split_sentences("We use e.g. CNNs. Fig. 3 shows it. Done.", "en") == ["We use e.g. CNNs.", "Fig. 3 shows it.", "Done."]
    urdu = build_script(["تعارف\nیہ ایک جملہ ہے۔"], language="ur", title="مقالہ", translated_from="en")
    assert urdu["sections"][0]["sentences"][0] == "یہ مقالے کا ترجمہ شدہ مطالعہ ہے۔"
    short = script_from_texts(["First point [2]. Second point."], language="en", title="Summary")
    assert short["sections"][0]["sentences"] == ["First point.", "Second point."]


def test_voices_registry_never_uses_a_wrong_language_voice(env):
    client, engine, _ = env
    english = client.get("/listen/voices", params={"language": "en"}).json()
    assert english["neural_available"] and all(voice["language"] == "en" for voice in english["voices"])
    assert english["voices"][0]["name"] == "Heart — English (US)" and "kokoro" not in str(english).lower()
    urdu = client.get("/listen/voices", params={"language": "ur"}).json()
    assert urdu["voices"] == [] and urdu["neural_available"] is False and urdu["browser"]["tier"] == "browser"
    started = client.post("/listen/sessions", json={"voice": "neural:af_heart", "language": "ur", "characters": 100})
    assert started.status_code == 422 and started.json()["detail"]["code"] == "voice_unavailable"
    with pytest.raises(tts.TTSUnavailable):
        tts.get_tts_router().synthesize("hola", voice_id="neural:af_heart", language="es")


def test_neural_listening_reserves_commits_per_chunk_caches_and_refunds(env, monkeypatch):
    client, engine, ledger = env
    monkeypatch.setenv("LISTEN_NEURAL_CREDITS_PER_MINUTE", "2")
    assert client.post("/listen/estimate", json={"characters": 2700, "language": "en", "voice": "browser"}).json()["credits"] == 0
    quote = client.post("/listen/estimate", json={"characters": 2700, "language": "en", "voice": "neural:af_heart"}).json()
    assert quote == {"minutes": 3.0, "credits": 6, "tier": "neural"}
    session = client.post("/listen/sessions", json={"voice": "neural:af_heart", "language": "en", "characters": 2700}).json()
    assert session["credits"] == 6
    assert ledger.usage("user:alice")["windows"][0]["used"] == 6  # reserved up front
    audio = client.post(f"/listen/sessions/{session['session_id']}/speak", json={"text": "Hello world. " * 34})
    assert audio.status_code == 200 and audio.headers["content-type"] == "audio/mpeg" and audio.content.startswith(b"ID3")
    again = client.post(f"/listen/sessions/{session['session_id']}/speak", json={"text": "Hello world. " * 34})
    assert again.headers["x-resora-cached"] == "1" and len(engine.calls) == 1
    done = client.post(f"/listen/sessions/{session['session_id']}/finish").json()
    assert done["charged"] == 2 and done["status"] == "committed"  # 2 × 442 chars ≈ 1 started minute × 2 credits; 4 refunded
    assert ledger.usage("user:alice")["windows"][0]["used"] == done["charged"]
    # stopping before anything was spoken refunds everything
    other = client.post("/listen/sessions", json={"voice": "neural:af_heart", "language": "en", "characters": 900}).json()
    assert client.post(f"/listen/sessions/{other['session_id']}/finish").json() == {"session_id": other["session_id"], "charged": 0, "status": "refunded"}
    assert ledger.usage("user:alice")["windows"][0]["used"] == done["charged"]
    # an engine failure is not charged and tells the player to fall back to the browser voice
    engine.fail = True
    third = client.post("/listen/sessions", json={"voice": "neural:af_heart", "language": "en", "characters": 900}).json()
    failed = client.post(f"/listen/sessions/{third['session_id']}/speak", json={"text": "A different sentence."})
    assert failed.status_code == 503 and failed.json()["detail"]["code"] == "voice_unavailable"
    assert client.post(f"/listen/sessions/{third['session_id']}/finish").json()["charged"] == 0


def test_resume_position_and_listen_later_queue(env):
    client, _, _ = env
    saved = client.put("/listen/progress", json={"item_id": "doc-1", "title": "Paper", "language": "ur", "section": 3, "sentence": 7, "total_sections": 9, "percent": 0.4, "rate": 1.25}).json()
    assert saved["section"] == 3 and saved["sentence"] == 7 and saved["rate"] == 1.25
    assert client.get("/listen/progress", params={"item_id": "doc-1"}).json()["items"][0]["percent"] == 0.4
    assert client.get("/listen/progress", headers=as_user("bob")).json()["items"] == []
    client.post("/listen/queue", json={"item_id": "doc-1", "title": "One"})
    client.post("/listen/queue", json={"item_id": "doc-2", "title": "Two"})
    items = client.post("/listen/queue", json={"item_id": "doc-1", "title": "One"}).json()["items"]
    assert [item["item_id"] for item in items] == ["doc-1", "doc-2"]
    items = client.post("/listen/queue/reorder", json={"ids": [items[1]["id"], items[0]["id"]]}).json()["items"]
    assert [item["item_id"] for item in items] == ["doc-2", "doc-1"]
    assert [item["item_id"] for item in client.delete("/listen/queue/doc-2").json()["items"]] == ["doc-1"]


def test_admin_role_is_server_enforced(env):
    client, _, _ = env
    assert client.get("/admin/overview").status_code == 403
    assert client.get("/admin/overview", headers=as_user("anonymous")).status_code == 401
    assert client.get("/admin/me", headers=as_user("root")).json() == {"user_id": "root", "admin": True}


def test_admin_metrics_users_grants_suspension_and_audit(env):
    client, _, ledger = env
    # alice buys Pro (sandbox), bob uses credits
    session = client.post("/billing/checkout", json={"kind": "subscription", "plan": "pro", "interval": "month", "currency": "usd"}).json()
    client.post(f"/billing/sandbox/{session['session_id']}/complete")
    ledger.commit(ledger.reserve("user:bob", "summary"))
    overview = client.get("/admin/overview", headers=as_user("root")).json()
    assert overview["subscriptions"]["trialing"] == 1 and overview["trialing"] == 1 and overview["plans"] == {"pro": 1}
    assert overview["active_users_30d"] >= 1 and overview["credits_by_action_30d"]["summary"] == 2
    users = client.get("/admin/users", headers=as_user("root")).json()
    assert {"alice", "bob"} <= {row["user_id"] for row in users["users"]}
    assert next(row for row in users["users"] if row["user_id"] == "alice")["plan"] == "pro"
    assert client.get("/admin/users", params={"q": "bo"}, headers=as_user("root")).json()["total"] == 1
    granted = client.post("/admin/users/bob/credits", json={"credits": 40, "reason": "Support goodwill"}, headers=as_user("root")).json()
    assert granted["balance"] == 40
    detail = client.get("/admin/users/bob", headers=as_user("root")).json()
    assert detail["credit_grants"][0]["credits_total"] == 40 and detail["audit"][0]["action"] == "user.grant_credits"
    assert client.post("/admin/users/root/suspension", json={"suspended": True}, headers=as_user("root")).json()["detail"]["code"] == "cannot_suspend_self"
    client.post("/admin/users/bob/suspension", json={"suspended": True, "reason": "abuse"}, headers=as_user("root"))
    blocked = client.get("/listen/queue", headers=as_user("bob"))
    assert blocked.status_code == 403 and blocked.json()["detail"]["code"] == "account_suspended"
    assert client.get("/site/status", headers=as_user("bob")).status_code == 200
    client.post("/admin/users/bob/suspension", json={"suspended": False}, headers=as_user("root"))
    assert client.get("/listen/queue", headers=as_user("bob")).status_code == 200
    actions = [entry["action"] for entry in client.get("/admin/audit", headers=as_user("root")).json()["entries"]]
    assert actions[:3] == ["user.unsuspend", "user.suspend", "user.grant_credits"]


def test_feature_flags_rollout_and_client_flags(env):
    client, _, _ = env
    flags = client.get("/admin/flags", headers=as_user("root")).json()["flags"]
    assert {"listen.neural_voices", "growth.referrals"} <= {flag["key"] for flag in flags}
    client.put("/admin/flags/beta.compare_v2", json={"enabled": True, "rollout": 50, "description": "New compare"}, headers=as_user("root"))
    buckets = [admin.flag_enabled("beta.compare_v2", f"user:u{index}") for index in range(400)]
    assert 140 < sum(buckets) < 260 and admin.flag_enabled("beta.compare_v2", "user:u7") == buckets[7]  # sticky
    client.put("/admin/flags/beta.compare_v2", json={"enabled": True, "rollout": 0, "allow_users": ["user:alice"]}, headers=as_user("root"))
    assert client.get("/site/flags").json()["flags"]["beta.compare_v2"] is True
    assert client.get("/site/flags", headers=as_user("bob")).json()["flags"]["beta.compare_v2"] is False
    assert client.put("/admin/flags/Bad Key!", json={"enabled": True}, headers=as_user("root")).status_code == 422
    client.put("/admin/flags/growth.referrals", json={"enabled": False}, headers=as_user("root"))
    assert client.get("/site/referral").status_code == 404


def test_dead_letter_retry_and_status_incidents(env, monkeypatch):
    client, _, _ = env
    entry = admin.record_dead_letter("billing_webhook", "sandbox", {"headers": {}, "body": "{}"}, "RuntimeError: db locked")
    monkeypatch.setattr(billing, "process_webhook", lambda provider, headers, body: 1)
    jobs = client.get("/admin/jobs", headers=as_user("root")).json()
    assert jobs["dead_letters"][0]["id"] == entry and jobs["dead_letters"][0]["status"] == "failed"
    assert client.post(f"/admin/jobs/dead-letters/{entry}/retry", headers=as_user("root")).json()["status"] == "resolved"
    status = client.get("/site/status").json()
    assert status["overall"] == "operational" and "billing" in status["components"]
    incident = client.post("/admin/incidents", json={"title": "Slow summaries", "component": "ai", "severity": "major", "status": "investigating", "message": "Looking into it"}, headers=as_user("root")).json()
    status = client.get("/site/status").json()
    assert status["components"]["ai"] == "partial_outage" and status["overall"] == "partial_outage" and status["incidents"][0]["title"] == "Slow summaries"
    client.put(f"/admin/incidents/{incident['id']}", json={"title": "Slow summaries", "component": "ai", "severity": "major", "status": "resolved", "message": "Fixed"}, headers=as_user("root"))
    assert client.get("/site/status").json()["overall"] == "operational"
    assert client.post("/admin/incidents", json={"title": "x x x", "component": "nope", "severity": "major", "status": "investigating"}, headers=as_user("root")).status_code == 422


def test_newsletter_double_opt_in_contact_and_cookieless_analytics(env, monkeypatch):
    client, _, _ = env
    from app.services.growth import service as growth

    sent: list[str] = []
    monkeypatch.setattr(growth, "_send_confirmation", lambda email, token, language: sent.append(token))
    assert client.post("/site/newsletter", json={"email": "x@example.org", "consent": False}).json()["detail"]["code"] == "consent_required"
    assert client.post("/site/newsletter", json={"email": "bad", "consent": True}).status_code == 422
    assert client.post("/site/newsletter", json={"email": "X@Example.org", "consent": True}).json() == {"status": "pending"}
    assert client.post("/site/newsletter/confirm", json={"token": sent[0]}).json() == {"status": "confirmed"}
    assert growth.waitlist_count() == {"confirmed": 1}
    assert client.post("/site/newsletter/unsubscribe", json={"token": sent[0]}).json() == {"status": "removed"}
    assert client.post("/site/contact", json={"email": "y@example.org", "message": "short"}).status_code == 422
    sent_message = client.post("/site/contact", json={"name": "Y", "email": "y@example.org", "topic": "billing", "message": "Please help with my invoice."})
    assert sent_message.status_code == 201
    assert client.post("/site/contact", json={"email": "bot@example.org", "message": "spam spam spam", "website": "http://spam"}).json()["id"] == "msg_ignored"
    messages = client.get("/admin/messages", headers=as_user("root")).json()["messages"]
    assert len(messages) == 1 and messages[0]["topic"] == "billing"
    for path in ["/", "/pricing", "/reader/0123456789abcdef0123"]:
        assert client.post("/site/pageview", json={"path": path, "referrer": "https://www.google.com/search?q=x", "language": "ur"}, headers={"user-agent": "Mozilla/5.0"}).status_code == 204
    client.post("/site/pageview", json={"path": "/x"}, headers={"user-agent": "Googlebot"})
    client.post("/site/pageview", json={"path": "/y"}, headers={"user-agent": "Mozilla/5.0", "dnt": "1"})
    traffic = growth.traffic_summary()
    assert traffic["pageviews"] == 3 and traffic["visitors"] == 1 and traffic["top_referrers"][0]["referrer"] == "google.com"
    assert {row["path"] for row in traffic["top_paths"]} == {"/", "/pricing", "/reader/:id"}
    with growth._db() as db:  # noqa: SLF001
        assert "127.0.0.1" not in str(db.all("select * from pageviews")) and "testclient" not in str(db.all("select * from pageviews"))


def test_referral_credits_for_both_people_once(env):
    client, _, _ = env
    code = client.get("/site/referral").json()["code"]
    assert len(code) == 8
    assert client.post("/site/referral/redeem", json={"code": code}).json()["detail"]["code"] == "referral_self"
    assert client.post("/site/referral/redeem", json={"code": "NOPE1234"}, headers=as_user("bob")).status_code == 404
    redeemed = client.post("/site/referral/redeem", json={"code": code.lower()}, headers=as_user("bob")).json()
    assert redeemed["credits"] == 50 and redeemed["balance"] == 50
    assert client.post("/site/referral/redeem", json={"code": code}, headers=as_user("bob")).json()["detail"]["code"] == "referral_used"
    mine = client.get("/site/referral").json()
    assert mine["invited"] == 1 and mine["credits_earned"] == 50 and billing.topup_balance("alice") == 50
    bob_code = client.get("/site/referral", headers=as_user("bob")).json()["code"]
    assert client.post("/site/referral/redeem", json={"code": bob_code}).json()["detail"]["code"] == "referral_circular"
