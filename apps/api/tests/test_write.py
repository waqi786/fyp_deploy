"""Write tab: grounded reviews and drafts from Library papers, unsupported-sentence flags, versions, exports
(DOCX / Markdown / LaTeX+bib / HTML), screening with PRISMA counts, and claim checks with validated quotes."""

import base64
import io
import json
import zipfile

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.deps import AuthContext, get_auth_context
from app.api.v1.endpoints import library, write
from app.core.config import settings
from app.services.write import grounding

PAPERS = [
    {"title": "Grounded decoding reduces hallucination", "authors": ["Ayesha Rahman", "Li Wei"], "year": 2024, "venue": "CVPR", "doi": "10.1/gd", "abstract": "Grounded decoding lowers object hallucination on the POPE benchmark. Accuracy rises from 83.9 to 86.9 percent."},
    {"title": "Contrastive decoding for captions", "authors": ["Noah Park"], "year": 2023, "venue": "NeurIPS", "abstract": "Contrastive decoding reduces hallucinated objects in image captioning with a transformer."},
    {"title": "Transformer baselines for captioning", "authors": ["Sara Ali", "Omar Khan", "Mei Lin"], "year": 2021, "venue": "ACL", "abstract": "A transformer baseline for image captioning; hallucination remains common."},
]


class Router:
    def __init__(self, text=None, verdicts=None):
        self.text, self.verdicts, self.calls = text, verdicts, []

    def complete(self, task, prompt, **kwargs):
        self.calls.append((task, json.loads(prompt), kwargs))
        if self.verdicts is not None:
            data = json.loads(prompt)
            rows = []
            for row, claim in zip(self.verdicts, data["claims"]):
                match = next((p["n"] for p in claim["passages"] if row.get("quote", "") and row["quote"].lower() in p["text"].lower()), 1)
                rows.append({**row, "n": match})
            return type("R", (), {"text": json.dumps({"claims": rows})})()
        return type("R", (), {"text": json.dumps({"text": self.text})})()


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
    monkeypatch.setattr(settings, "database_url", f"sqlite:///{tmp_path / 'write.sqlite3'}")
    app = FastAPI()
    app.include_router(write.router, prefix="/write")
    app.include_router(library.router, prefix="/library")
    app.dependency_overrides[get_auth_context] = lambda: AuthContext(user_id="owner-1", source="test", verified=True)
    return TestClient(app)


def seed(client):
    project = client.post("/library/lists", json={"kind": "project", "name": "Hallucination review"}).json()
    items = client.post("/library/items", json={"papers": PAPERS, "source": "search", "list_id": project["id"]}).json()["items"]
    return project, items


def num(doc, title_start):
    return next(index for index, source in enumerate(doc["sources"], start=1) if source and source["title"].startswith(title_start))


def use_router(monkeypatch, router):
    import app.services.ai_router as ai_router

    monkeypatch.setattr(ai_router, "get_default_router", lambda: router)
    return router


def test_review_outline_grounded_section_and_flags(client, monkeypatch):
    project, items = seed(client)
    doc = client.post("/write/documents", json={"kind": "review", "title": "Hallucination in VLMs", "style": "thematic", "project_id": project["id"]}).json()
    assert len(doc["sources"]) == 3 and doc["sections"][0]["heading"] == "Introduction" and doc["sections"][-1]["heading"] == "Conclusion"
    assert any(section["heading"] in {"Hallucination", "Image captioning"} for section in doc["sections"])
    g, c = num(doc, "Grounded"), num(doc, "Contrastive")
    text = f"Grounded decoding raises accuracy from 83.9 to 86.9 percent [{g}]. Contrastive decoding also helps [{c}]. It works in all languages. It reaches 99.0 percent [{g}]."
    router = use_router(monkeypatch, Router(text))
    section = doc["sections"][0]
    written = client.post(f"/write/documents/{doc['id']}/sections/{section['id']}/write", json={"instruction": "Keep it short"}).json()
    first = written["sections"][0]
    assert first["status"] == "generated" and first["text"].startswith("Grounded decoding")
    assert first["unsupported"] == ["It works in all languages.", f"It reaches 99.0 percent [{g}]."]  # no citation; number not in source
    assert router.calls[0][2]["user_content"] is True and {source["n"] for source in router.calls[0][1]["sources"]} == {1, 2, 3}

    # A writer that cites a source that does not exist is rejected.
    use_router(monkeypatch, Router("Something [7] about everything in the papers here."))
    assert client.post(f"/write/documents/{doc['id']}/sections/{section['id']}/write", json={}).status_code == 503

    # Editing marks the section edited and re-checks support; versions keep the previous text.
    sections = written["sections"]
    sections[0] = {**sections[0], "text": f"Grounded decoding lowers object hallucination [{g}]."}
    edited = client.patch(f"/write/documents/{doc['id']}", json={"sections": sections}).json()
    assert edited["sections"][0]["status"] == "edited" and edited["sections"][0]["unsupported"] == []
    versions = client.get(f"/write/documents/{doc['id']}/versions").json()["versions"]
    assert versions and versions[0]["label"].startswith("Before rewriting")
    restored = client.post(f"/write/documents/{doc['id']}/versions/{versions[0]['id']}/restore").json()
    assert restored["sections"][0]["text"].startswith("Grounded decoding raises")


def test_exports_convert_citations_and_list_only_cited_sources(client):
    project, items = seed(client)
    doc = client.post("/write/documents", json={"kind": "draft", "title": "Intro draft", "style": "introduction", "project_id": project["id"], "citation_style": "apa"}).json()
    sections = doc["sections"]
    sections[0]["text"] = f"Hallucination is common [{num(doc, 'Transformer')}]. Grounding reduces it [{num(doc, 'Grounded')}]."
    client.patch(f"/write/documents/{doc['id']}", json={"sections": sections})
    md = client.post(f"/write/documents/{doc['id']}/export", json={"format": "markdown"}).json()["content"]
    assert "(Ali et al., 2021)" in md and "(Rahman & Wei, 2024)" in md and "Park" not in md
    client.patch(f"/write/documents/{doc['id']}", json={"citation_style": "ieee"})
    ieee = client.post(f"/write/documents/{doc['id']}/export", json={"format": "markdown"}).json()["content"]
    assert "common [1]. Grounding reduces it [2]." in ieee and ieee.index("Ali") < ieee.index("Rahman")
    latex = client.post(f"/write/documents/{doc['id']}/export", json={"format": "latex"}).json()
    assert "\\cite{ali2021transformer}" in latex["content"] and "@article{rahman2024grounded" in latex["bib"]
    docx = client.post(f"/write/documents/{doc['id']}/export", json={"format": "docx"}).json()
    archive = zipfile.ZipFile(io.BytesIO(base64.b64decode(docx["base64"])))
    assert "Hallucination is common [1]" in archive.read("word/document.xml").decode() and "word/styles.xml" in archive.namelist()
    html = client.post(f"/write/documents/{doc['id']}/export", json={"format": "html", "rtl": True}).json()["content"]
    assert "dir='rtl'" in html and "<ol class='refs numbered'>" in html
    check = client.get(f"/write/documents/{doc['id']}/check").json()
    assert check["uncited_sources"] == [num(doc, "Contrastive")] and check["broken_markers"] == []


def test_sources_are_append_only(client):
    project, items = seed(client)
    doc = client.post("/write/documents", json={"kind": "draft", "title": "x", "style": "abstract", "item_ids": [items[0]["id"]]}).json()
    doc = client.post(f"/write/documents/{doc['id']}/sources", json={"item_ids": [items[1]["id"], items[0]["id"]]}).json()
    assert [source["title"] for source in doc["sources"]] == [PAPERS[0]["title"], PAPERS[1]["title"]]
    doc = client.delete(f"/write/documents/{doc['id']}/sources/1").json()
    assert doc["sources"][0] is None and doc["sources"][1]["title"] == PAPERS[1]["title"]


def test_screening_and_prisma(client):
    project, items = seed(client)
    screening = client.post("/write/screenings", json={"name": "Review screening", "project_id": project["id"]}).json()
    assert screening["prisma"]["identified"] == 3
    bib = "@article{a, title={Grounded decoding reduces hallucination}, author={Rahman, Ayesha}, year={2024}, doi={10.1/gd}}\n@article{b, title={A new unrelated record}, year={2020}}"
    imported = client.post(f"/write/screenings/{screening['id']}/records", json={"content": bib, "filename": "more.bib"}).json()
    assert imported["added"] == 1 and imported["duplicates"] == 1
    records = [record for record in imported["screening"]["records"] if not record["duplicate_of"]]
    ids = {record["title"]: record["id"] for record in records}
    path = f"/write/screenings/{screening['id']}/records"
    client.patch(f"{path}/{ids['A new unrelated record']}", json={"ta_decision": "exclude", "ta_reason": "Off topic"})
    client.patch(f"{path}/{ids[PAPERS[0]['title']]}", json={"ta_decision": "include"})
    client.patch(f"{path}/{ids[PAPERS[1]['title']]}", json={"ta_decision": "include"})
    client.patch(f"{path}/{ids[PAPERS[1]['title']]}", json={"ft_decision": "exclude", "ft_reason": "No evaluation"})
    result = client.patch(f"{path}/{ids[PAPERS[0]['title']]}", json={"ft_decision": "include"}).json()
    assert result["prisma"] == {"identified": 5, "duplicates": 1, "screened": 4, "screen_excluded": 1, "screen_pending": 1, "full_text_assessed": 2,
                                "full_text_excluded": 1, "full_text_pending": 0, "full_text_reasons": [{"reason": "No evaluation", "count": 1}], "included": 1}
    # Changing the first decision to exclude clears the full-text decision.
    cleared = client.patch(f"{path}/{ids[PAPERS[0]['title']]}", json={"ta_decision": "exclude"}).json()["record"]
    assert cleared["ft_decision"] is None
    client.patch(f"{path}/{ids[PAPERS[0]['title']]}", json={"ta_decision": "include"})
    client.patch(f"{path}/{ids[PAPERS[0]['title']]}", json={"ft_decision": "include"})
    assert client.post(f"/write/screenings/{screening['id']}/to-library", json={}).json() == {"saved": 1, "already_saved": 1}


def test_claims_ai_validated_and_keyword_fallback(client, monkeypatch):
    project, items = seed(client)
    text = "Grounded decoding lowers object hallucination on POPE. Contrastive decoding removes all hallucinations forever."
    use_router(monkeypatch, Router(verdicts=[
        {"verdict": "supported", "quote": "Grounded decoding lowers object hallucination on the POPE benchmark.", "strength": "moderate"},
        {"verdict": "mixed", "quote": "Contrastive decoding reduces hallucinated objects", "strength": "limited", "safer": "Contrastive decoding reduces hallucinated objects in captions."},
    ]))
    body = client.post("/write/claims", json={"text": text, "project_id": project["id"]}).json()
    assert body["mode"] == "ai" and [claim["verdict"] for claim in body["claims"]] == ["supported", "mixed"]
    assert body["claims"][1]["safer"].startswith("Contrastive decoding reduces") and [source["n"] for source in body["sources"]] == [1, 2, 3]
    use_router(monkeypatch, Router(verdicts=[{"verdict": "supported", "quote": "Words that are not in any passage at all.", "strength": "strong"}, {"verdict": "not_found"}]))
    fallback = client.post("/write/claims", json={"text": text, "project_id": project["id"]}).json()
    assert fallback["mode"] == "keywords" and fallback["claims"][0]["verdict"] == "supported" and fallback["claims"][0]["safer"] is None
    assert client.post("/write/claims", json={"text": "Too short."}).status_code == 422


def test_privacy_and_validation(client, tmp_path, monkeypatch):
    project, items = seed(client)
    doc = client.post("/write/documents", json={"kind": "review", "title": "Mine", "style": "narrative", "project_id": project["id"]}).json()
    assert client.post("/write/documents", json={"kind": "review", "title": "x", "style": "abstract"}).status_code == 422
    other = FastAPI()
    other.include_router(write.router, prefix="/write")
    other.dependency_overrides[get_auth_context] = lambda: AuthContext(user_id="owner-2", source="test", verified=True)
    stranger = TestClient(other)
    assert stranger.get(f"/write/documents/{doc['id']}").status_code == 404
    assert stranger.get("/write/documents").json() == []
    assert stranger.post("/write/claims", json={"text": "Grounded decoding lowers object hallucination on POPE."}).status_code == 422


def test_outline_styles():
    sources = [{"title": p["title"], "abstract": p["abstract"], "year": p["year"]} for p in PAPERS]
    chrono = [section["heading"] for section in grounding.outline(sources, "chronological")]
    assert chrono[0] == "Introduction" and any("2021" in heading for heading in chrono)
    methods = grounding.outline(sources, "methodological")
    assert any(section["heading"] == "Transformer" for section in methods)


def test_themes_flag_mixed_evidence_and_become_the_outline(client):
    project = client.post("/library/lists", json={"kind": "project", "name": "Theme review"}).json()
    papers = PAPERS + [{"title": "Captioning transformers revisited", "authors": ["Mei Lin"], "year": 2025, "venue": "ICCV", "abstract": "Contrastive decoding does not reduce hallucination in image captioning for long captions."}]
    client.post("/library/items", json={"papers": papers, "source": "search", "list_id": project["id"]})
    doc = client.post("/write/documents", json={"kind": "review", "title": "Themes", "style": "narrative", "project_id": project["id"]}).json()
    themes = client.get(f"/write/documents/{doc['id']}/themes").json()["themes"]
    captioning = next(theme for theme in themes if theme["label"] == "Image captioning")
    assert len(captioning["papers"]) == 3 and captioning["evidence"] == "mixed" and captioning["quotes"]
    chosen = [{"label": "Image captioning", "papers": captioning["papers"]}, {"label": "Ignored", "papers": [99]}]
    rebuilt = client.post(f"/write/documents/{doc['id']}/outline", json={"style": "thematic", "themes": chosen}).json()
    headings = [section["heading"] for section in rebuilt["sections"]]
    assert headings == ["Introduction", "Image captioning", "Gaps and future directions", "Conclusion"]
    assert rebuilt["sections"][1]["papers"] == captioning["papers"]
