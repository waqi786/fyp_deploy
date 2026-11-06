"""Gaps tab: evidence-levelled signals with the papers behind every count, trends/people/datasets, saved states,
turning a signal into a Library idea, consensus (validated AI + keyword fallback) and grounded AI hypotheses."""

import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.deps import AuthContext, get_auth_context
from app.api.v1.endpoints import gap, library
from app.core.config import settings
from app.services.gaps import analysis

PAPERS = [
    {"id": "p1", "title": "Transformer models for chest X-ray classification", "abstract": "We train a transformer on the CheXpert dataset for classification in radiology. Accuracy improves over CNN baselines. A limitation is that we only evaluate adult patients.", "year": 2021, "authors": ["A. Khan", "B. Lee"], "citation_count": 40},
    {"id": "p2", "title": "Vision transformers in clinical imaging", "abstract": "A transformer approach for clinical imaging classification on the CheXpert dataset. Future work should study children.", "year": 2022, "authors": ["B. Lee"], "citation_count": 25},
    {"id": "p3", "title": "Transformer pretraining for radiology reports", "abstract": "Transformer pretraining improves summarization of radiology reports on the MIMIC-III dataset.", "year": 2023, "authors": ["C. Diaz"], "citation_count": 12},
    {"id": "p4", "title": "CNN ensembles for X-ray triage", "abstract": "We use a CNN ensemble on the CheXpert dataset for classification. Limitation: we only evaluate adult patients from one hospital.", "year": 2020, "authors": ["A. Khan"], "citation_count": 55},
    {"id": "p5", "title": "Convolutional networks for pediatric pneumonia", "abstract": "A convolutional neural network detects pneumonia in children using the CheXpert dataset.", "year": 2021, "authors": ["D. Osei"], "citation_count": 18},
    {"id": "p6", "title": "Federated learning for hospital imaging", "abstract": "Federated learning across hospitals for classification on the CheXpert dataset. Accuracy does not improve for rare classes.", "year": 2024, "authors": ["E. Park", "A. Khan"], "citation_count": 4},
    {"id": "p7", "title": "Federated transformers for clinical text", "abstract": "Federated learning of clinical language models. Results are limited to English notes.", "year": 2025, "authors": ["E. Park"], "citation_count": 1},
    {"id": "p8", "title": "Self-supervised CNNs for radiology", "abstract": "A CNN with self-supervised pretraining on the CheXpert dataset improves segmentation.", "year": 2019, "authors": ["F. Rossi"], "citation_count": 70},
]


class FakeCredits:
    """Unlimited credits so tests never depend on a shared usage ledger."""

    def reserve(self, *args, **kwargs):
        return "reservation"

    def refund(self, reservation):
        pass

    def commit(self, reservation, used):
        pass

    def cost(self, action):
        return 1


@pytest.fixture
def client(tmp_path, monkeypatch):
    import app.services.credits.service as credit_service

    monkeypatch.setattr(credit_service, "get_credit_service", lambda: FakeCredits())
    monkeypatch.setattr(settings, "database_url", f"sqlite:///{tmp_path / 'gaps.sqlite3'}")
    app = FastAPI()
    app.include_router(gap.router, prefix="/gap")
    app.include_router(library.router, prefix="/library")
    app.dependency_overrides[get_auth_context] = lambda: AuthContext(user_id="owner-1", source="test", verified=True)
    return TestClient(app)


def run(client, papers=PAPERS, scope=None):
    response = client.post("/gap/signals", json={"papers": papers, "scope": scope or {"kind": "topic", "label": "Chest X-ray AI"}, "current_year": 2026})
    assert response.status_code == 200, response.text
    return response.json()


def test_signals_are_evidence_backed_and_levelled(client):
    body = run(client)
    assert body["paper_count"] == 8 and body["scope_key"] == "topic:chest x-ray ai"
    kinds = {signal["kind"] for signal in body["signals"]}
    assert {"combination_untested", "benchmark_concentration", "repeated_limitation"} <= kinds
    for signal in body["signals"]:
        assert signal["level"] in {"strong", "moderate", "limited"}
        assert all(paper_id in {p["id"] for p in PAPERS} for ids in signal["papers"].values() for paper_id in ids)
        assert "weight" not in signal  # internal ranking never leaves the server
    bench = next(signal for signal in body["signals"] if signal["kind"] == "benchmark_concentration")
    assert bench["a"]["label"] == "CheXpert" and bench["counts"]["a"] == 6 and len(bench["papers"]["a"]) == 6
    # "Future work should study children" is not evidence that children were studied: only p5 counts, so no signal.
    assert not [s for s in body["signals"] if s["kind"].startswith("combination") and s["b"]["label"] == "Children"]
    untested = next(s for s in body["signals"] if s["kind"] == "combination_untested")
    assert untested["counts"]["both"] == 0 and untested["papers"]["both"] == []
    # Stable ids: the same input gives the same signal ids.
    assert [s["id"] for s in run(client)["signals"]] == [s["id"] for s in body["signals"]]


def test_trends_people_and_datasets(client):
    body = run(client)
    assert [row["year"] for row in body["trends"]["years"]] == [2019, 2020, 2021, 2022, 2023, 2024, 2025]
    assert body["trends"]["series"]["method"][0]["label"] in {"Transformer", "CNN"}
    khan = next(person for person in body["people"]["researchers"] if person["name"] == "A. Khan")
    assert khan["papers"] == 3 and "B. Lee" in khan["collaborators"]
    chexpert = next(row for row in body["datasets"] if row["name"] == "CheXpert")
    assert chexpert["papers"] == 6 and "Classification" in chexpert["tasks"]


def test_states_and_idea_go_to_library(client):
    body = run(client)
    first = body["signals"][0]
    assert client.put(f"/gap/states/{first['id']}", json={"scope_key": body["scope_key"], "state": "dismissed"}).status_code == 204
    assert run(client)["states"] == {first["id"]: "dismissed"}
    project = client.post("/library/lists", json={"kind": "project", "name": "Thesis"}).json()
    idea = client.post(f"/gap/states/{first['id']}/idea", json={"scope_key": body["scope_key"], "title": "Test transformers on children", "project_id": project["id"]}).json()
    notes = client.get("/library/notes", params={"kind": "idea"}).json()
    assert notes[0]["id"] == idea["idea_id"] and notes[0]["project_id"] == project["id"]
    assert run(client)["states"][first["id"]] == "idea"
    client.put(f"/gap/states/{first['id']}", json={"scope_key": body["scope_key"], "state": None})
    assert run(client)["states"] == {}


def test_consensus_validates_quotes_and_falls_back(client, monkeypatch):
    import app.services.ai_router as ai_router

    class Router:
        def __init__(self, quote):
            self.quote = quote

        def complete(self, task, prompt, **kwargs):
            papers = json.loads(prompt)["papers"]
            rows = [{"paper_id": p["paper_id"], "stance": "supports" if p["paper_id"] == "p1" else "not_addressed", "reason": "Reports higher accuracy.", "quote": self.quote if p["paper_id"] == "p1" else ""} for p in papers]
            return type("R", (), {"text": json.dumps({"papers": rows})})()

    monkeypatch.setattr(ai_router, "get_default_router", lambda: Router("Accuracy improves over CNN baselines."))
    body = client.post("/gap/consensus", json={"question": "Do transformers improve accuracy over CNNs?", "papers": PAPERS[:3]}).json()
    assert body["mode"] == "ai" and body["counts"]["supports"] == 1 and body["rows"][0]["quote"] == "Accuracy improves over CNN baselines."

    monkeypatch.setattr(ai_router, "get_default_router", lambda: Router("A quote that is not in the paper at all."))
    fallback = client.post("/gap/consensus", json={"question": "Do transformers improve accuracy over CNNs?", "papers": PAPERS[:3]}).json()
    assert fallback["mode"] == "keywords" and fallback["rows"][0]["stance"] == "supports"


def test_hypotheses_must_cite_given_papers(client, monkeypatch):
    import app.services.ai_router as ai_router

    class Router:
        def __init__(self, ids):
            self.ids = ids

        def complete(self, task, prompt, **kwargs):
            return type("R", (), {"text": json.dumps({"hypotheses": [{"title": "Evaluate transformers on paediatric X-rays", "missing_evidence": "No paediatric test set.", "paper_ids": self.ids}]})})()

    monkeypatch.setattr(ai_router, "get_default_router", lambda: Router(["p1", "p5"]))
    body = client.post("/gap/hypotheses", json={"papers": PAPERS, "focus": "chest x-ray"}).json()
    assert body["hypotheses"][0]["level"] == "hypothesis" and body["hypotheses"][0]["papers"]["a"] == ["p1", "p5"]
    monkeypatch.setattr(ai_router, "get_default_router", lambda: Router(["p1", "invented"]))
    assert client.post("/gap/hypotheses", json={"papers": PAPERS, "focus": "chest x-ray"}).status_code == 503


def test_small_sets_and_anonymous(client, tmp_path, monkeypatch):
    assert client.post("/gap/signals", json={"papers": PAPERS[:1], "scope": {"kind": "topic", "label": "x"}}).status_code == 422
    app = FastAPI()
    app.include_router(gap.router, prefix="/gap")
    app.dependency_overrides[get_auth_context] = lambda: AuthContext(user_id="anonymous", source="anonymous", verified=False)
    assert TestClient(app).post("/gap/signals", json={"papers": PAPERS, "scope": {"kind": "topic", "label": "x"}}).status_code == 401


def test_legacy_analyze_still_works(client):
    papers = [{"paper_id": p["id"], "title": p["title"], "abstract": p["abstract"], "year": p["year"], "source": "test", "authors": [{"name": a} for a in p["authors"]]} for p in PAPERS[:3]]
    assert client.post("/gap/analyze", json={"papers": papers, "focus": "x"}).status_code == 200


def test_analysis_unit_no_signal_from_two_unrelated_papers():
    result = analysis.analyze([analysis.Paper(id="a", title="On poetry"), analysis.Paper(id="b", title="On cooking")], current_year=2026)
    assert result["signals"] == []


def test_one_limitation_stated_with_several_words_is_one_signal():
    papers = [
        analysis.Paper(id=f"q{n}", title=f"Study {n}", abstract="We evaluate a model. A limitation is that evaluation uses only English data from social media.", year=2020 + n, authors=[f"Author {n}"])
        for n in range(3)
    ]
    result = analysis.analyze(papers, current_year=2026)
    limits = [signal for signal in result["signals"] if signal["kind"] == "repeated_limitation"]
    assert len(limits) == 1
    assert "English" in limits[0]["a"]["label"] and limits[0]["counts"]["a"] == 3
    assert sorted(limits[0]["papers"]["a"]) == ["q0", "q1", "q2"]


def test_recommendations_have_one_checkable_reason(client):
    saved = [PAPERS[0], PAPERS[6]]  # CheXpert transformer paper; federated clinical text with an English-only limitation
    candidates = [
        {"id": "c1", "title": "Transformers for pediatric chest X-ray classification on CheXpert", "abstract": "A transformer model for classification in radiology on the CheXpert dataset.", "year": 2025, "authors": ["Z. Noor"], "citation_count": 3},
        {"id": "c2", "title": "Multilingual clinical notes: beyond English", "abstract": "We extend clinical language models to Urdu and Arabic notes, addressing notes limited to English.", "year": 2025, "authors": ["Y. Haq"]},
        {"id": "c3", "title": "Crop yield forecasting with satellites", "abstract": "Forecasting crop yield.", "year": 2024, "authors": ["X. Lee"]},
        {"id": "p1", "title": PAPERS[0]["title"], "abstract": PAPERS[0]["abstract"], "year": 2021, "authors": []},
    ]
    response = client.post("/gap/recommendations", json={"saved": saved, "candidates": candidates, "notes": ["Results are limited to English notes; test other languages"], "current_year": 2026})
    assert response.status_code == 200
    rows = response.json()["recommendations"]
    ids = [row["paper_id"] for row in rows]
    assert "c1" in ids and "c3" not in ids and "p1" not in ids  # unrelated and already-saved papers are never suggested
    first = next(row for row in rows if row["paper_id"] == "c1")
    assert first["reason"]["kind"] in {"extends", "same_dataset"} and first["reason"]["paper_title"] == PAPERS[0]["title"]
    assert any(row["paper_id"] == "c2" and row["reason"]["kind"] == "addresses_limitation" for row in rows)


def test_people_suggest_collaborators_with_shared_topics():
    papers = [
        analysis.Paper(id="a1", title="Transformer classification on CheXpert", abstract="A transformer for classification on the CheXpert dataset.", year=2022, authors=["A. One"]),
        analysis.Paper(id="a2", title="Transformer classification for X-ray", abstract="Transformer classification using CheXpert.", year=2023, authors=["B. Two"]),
        analysis.Paper(id="a3", title="Crop forecasting", abstract="Forecasting crop yield with random forests.", year=2023, authors=["C. Three"]),
    ]
    people = analysis.analyze(papers, current_year=2026)["people"]["researchers"]
    one = next(row for row in people if row["name"] == "A. One")
    assert [entry["name"] for entry in one["suggested"]] == ["B. Two"]
    assert "Transformer" in one["suggested"][0]["shared"]
