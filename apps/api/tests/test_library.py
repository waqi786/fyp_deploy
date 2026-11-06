"""Library tab: save from anywhere (deduplicated), status/tags/bulk, projects and collections, notes, ideas, tasks,
citations (styles, exports, imports), Ask with grounded citations, and strict owner isolation. No network."""

import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.deps import AuthContext, get_auth_context
from app.api.v1.endpoints import library
from app.core.config import settings
from app.services.library import ask as library_ask
from app.services.library import resolve

PAPER = {"title": "Attention Is All You Need", "authors": ["Ashish Vaswani", "Noam Shazeer"], "year": 2017, "venue": "NeurIPS", "doi": "https://doi.org/10.48550/arXiv.1706.03762", "abstract": "The Transformer relies entirely on attention."}
OTHER = {"title": "Grounded decoding reduces hallucination in vision-language models", "authors": ["A. Rahman"], "year": 2024, "venue": "CVPR", "abstract": "Decoding grounded in image regions lowers object hallucination on POPE."}


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


def client_for(tmp_path, monkeypatch, user="owner-1"):
    import app.services.credits.service as credit_service

    monkeypatch.setattr(credit_service, "get_credit_service", lambda: FakeCredits())
    monkeypatch.setattr(settings, "database_url", f"sqlite:///{tmp_path / 'library.sqlite3'}")
    app = FastAPI()
    app.include_router(library.router, prefix="/library")
    app.dependency_overrides[get_auth_context] = lambda: AuthContext(user_id=user, source="test", verified=True)
    return TestClient(app)


@pytest.fixture
def client(tmp_path, monkeypatch):
    return client_for(tmp_path, monkeypatch)


def save(client, *papers, **extra):
    response = client.post("/library/items", json={"papers": list(papers), "source": "search", **extra})
    assert response.status_code == 200, response.text
    return response.json()


def test_saving_twice_keeps_one_copy_and_lookup_finds_it(client):
    first = save(client, PAPER)["items"][0]
    assert first["doi"] == "10.48550/arxiv.1706.03762" and first["status"] == "to_read" and first["authors"] == ["Ashish Vaswani", "Noam Shazeer"]
    again = save(client, {**PAPER, "doi": "10.48550/ARXIV.1706.03762"}, tags=["transformers"])
    assert again["already_saved"] == [first["id"]] and again["items"][0]["tags"] == ["transformers"]
    assert len(client.get("/library/items").json()) == 1
    lookup = client.post("/library/items/lookup", json={"papers": [PAPER, OTHER]}).json()
    assert lookup["item_ids"] == [first["id"], None]
    assert "owner_id" not in first and "paper_key" in first


def test_status_tags_bulk_and_overview(client):
    a = save(client, PAPER)["items"][0]
    b = save(client, OTHER, read_later=True)["items"][0]
    opened = client.patch(f"/library/items/{a['id']}", json={"opened": True}).json()
    assert opened["status"] == "reading" and opened["opened_at"]
    client.patch(f"/library/items/{a['id']}", json={"important": True, "tags": ["nlp", "NLP", " #core "]})
    assert client.get("/library/items").json()[1]["tags"] == ["nlp", "core"]
    assert client.post("/library/items/bulk", json={"ids": [a["id"], b["id"]], "action": "set_status", "value": "read"}).json() == {"updated": 2}
    client.post("/library/items/bulk", json={"ids": [b["id"]], "action": "add_tag", "value": "vision"})
    assert client.post("/library/items/bulk", json={"ids": [a["id"]], "action": "set_status", "value": "done"}).status_code == 422
    overview = client.get("/library/overview").json()
    assert overview["counts"]["saved"] == 2 and overview["counts"]["read"] == 2 and overview["counts"]["important"] == 1 and overview["counts"]["read_later"] == 1
    assert {"tag": "vision", "count": 1} in overview["tags"]


def test_projects_collections_notes_ideas_and_tasks(client):
    project = client.post("/library/lists", json={"kind": "project", "name": "Hallucination thesis", "description": "Chapter 2"}).json()
    item = save(client, OTHER, list_id=project["id"])["items"][0]
    assert item["list_ids"] == [project["id"]]
    collection = client.post("/library/lists", json={"kind": "collection", "name": "To cite"}).json()
    client.post("/library/items/bulk", json={"ids": [item["id"]], "action": "add_to_list", "value": collection["id"]})
    note = client.post("/library/notes", json={"body": "Region grounding is the key idea.", "quote": "lowers object hallucination", "page": 3, "item_id": item["id"], "project_id": project["id"]}).json()
    idea = client.post("/library/notes", json={"kind": "idea", "title": "Try grounding on video", "project_id": project["id"]}).json()
    assert idea["status"] == "new" and note["page"] == 3
    client.patch(f"/library/notes/{idea['id']}", json={"status": "exploring"})
    task = client.post("/library/tasks", json={"title": "Read related work", "due_date": "2026-01-10", "project_id": project["id"], "priority": "high"}).json()
    done = client.patch(f"/library/tasks/{task['id']}", json={"done": True}).json()
    assert done["done"] and done["completed_at"]
    detail = client.get(f"/library/lists/{project['id']}").json()
    assert detail["item_ids"] == [item["id"]] and detail["stats"] == {"papers": 1, "to_read": 1, "important": 0, "notes": 1, "ideas": 1, "tasks_open": 0}
    assert [entry["name"] for entry in client.get("/library/lists", params={"kind": "collection"}).json()] == ["To cite"]
    # Deleting a project keeps its papers, notes and tasks.
    assert client.delete(f"/library/lists/{project['id']}").status_code == 204
    assert len(client.get("/library/items").json()) == 1
    assert client.get("/library/notes").json()[0]["project_id"] is None or len(client.get("/library/notes").json()) == 2
    assert client.post("/library/notes", json={"body": "  "}).status_code == 422
    assert client.post("/library/tasks", json={"title": "x", "due_date": "10/01/2026"}).status_code == 422


def test_citations_styles_and_exports(client):
    a = save(client, PAPER)["items"][0]
    save(client, OTHER)
    apa = client.post("/library/citations/format", json={"style": "apa"}).json()
    assert [entry["text"][:12] for entry in apa["entries"]] == ["Rahman, A. (", "Vaswani, A.,"]  # alphabetical
    assert any(part["italic"] and part["text"] == "NeurIPS" for part in apa["entries"][1]["parts"])
    ieee = client.post("/library/citations/format", json={"style": "ieee", "item_ids": [a["id"]]}).json()
    assert ieee["entries"][0]["text"].startswith("[1] A. Vaswani and N. Shazeer, “Attention Is All You Need,” NeurIPS, 2017, doi: 10.48550/arxiv.1706.03762.")
    for fmt, marker in [("bibtex", "@article{vaswani2017attention"), ("biblatex", "journaltitle = {NeurIPS}"), ("ris", "TY  - JOUR"), ("endnote", "%0 Journal Article"), ("csljson", '"family": "Vaswani"'), ("markdown", "*NeurIPS*")]:
        body = client.post("/library/citations/export", json={"format": fmt, "item_ids": [a["id"]]}).json()
        assert marker in body["content"], fmt
    assert client.post("/library/citations/export", json={"format": "ris", "item_ids": []}).status_code == 422


def test_import_bib_ris_csl_and_identifiers_with_dedup(client, monkeypatch):
    save(client, PAPER)
    bib = "@article{v17, title={Attention Is All You Need}, author={Vaswani, Ashish and Shazeer, Noam}, year={2017}, doi={10.48550/arXiv.1706.03762}}\n@inproceedings{k, title = {M{\\\"u}ller's {Grounded} Decoding}, author = \"M{\\\"u}ller, J.\", booktitle={CVPR}, year=2024, keywords={vision, decoding}}"
    result = client.post("/library/citations/import", json={"content": bib, "filename": "refs.bib"}).json()
    assert result["format"] == "bibtex" and result["added"] == 1 and result["already_saved"] == 1
    imported = next(item for item in result["items"] if item["year"] == 2024)
    assert imported["title"] == "Müller's Grounded Decoding" and imported["venue"] == "CVPR" and imported["tags"] == ["vision", "decoding"]
    ris = "TY  - JOUR\nTI  - A RIS paper\nAU  - Doe, Jane\nPY  - 2020\nT2  - Nature\nER  - \n"
    assert client.post("/library/citations/import", json={"content": ris}).json()["added"] == 1
    csl = json.dumps([{"title": "A CSL paper", "author": [{"family": "Roe", "given": "R."}], "issued": {"date-parts": [[2021]]}}])
    assert client.post("/library/citations/import", json={"content": csl}).json()["format"] == "csljson"

    async def fake(identifiers):
        return [(value, {"title": "Resolved by DOI", "authors": ["Kim, Lee"], "year": 2022, "doi": value} if kind == "doi" else None) for kind, value in identifiers]

    monkeypatch.setattr(resolve, "resolve_identifiers", fake)
    ids = client.post("/library/citations/import", json={"content": "10.1038/nature12373\narXiv:2301.01234"}).json()
    assert ids["format"] == "ids" and ids["added"] == 1 and ids["not_found"] == ["2301.01234"]
    assert client.post("/library/citations/import", json={"content": "nothing useful here"}).status_code == 422
    assert len(client.get("/library/items").json()) == 5


def test_ask_answers_only_from_the_library(client, monkeypatch):
    save(client, PAPER, OTHER)
    client.post("/library/notes", json={"body": "My idea: combine grounding with contrastive decoding."})
    calls = []

    class Router:
        def complete(self, task, prompt, **kwargs):
            calls.append(kwargs)
            sources = json.loads(prompt)["sources"]
            assert "Grounded decoding" in sources
            return type("R", (), {"text": json.dumps({"answer": "Grounding image regions lowers hallucination [1].", "not_found": False})})()

    import app.services.ai_router as ai_router

    monkeypatch.setattr(ai_router, "get_default_router", lambda: Router())
    body = client.post("/library/ask", json={"question": "Which paper reduces hallucination?"}).json()
    assert body["mode"] == "answer" and "[1]" in body["answer"] and body["sources"][0]["title"].startswith("Grounded decoding")
    assert calls[0]["user_content"] is True

    class Inventing(Router):
        def complete(self, task, prompt, **kwargs):
            return type("R", (), {"text": json.dumps({"answer": "See [9].", "not_found": False})})()

    monkeypatch.setattr(ai_router, "get_default_router", lambda: Inventing())
    fallback = client.post("/library/ask", json={"question": "Which paper reduces hallucination?"}).json()
    assert fallback["mode"] == "matches" and fallback["answer"] is None and fallback["sources"]
    assert client.post("/library/ask", json={"question": "quantum chromodynamics lattice"}).json()["sources"] == []


def test_time_phrases():
    from datetime import date

    today = date(2026, 11, 4)
    assert library_ask.time_window("papers from last month", today) == (date(2026, 9, 3), date(2026, 10, 7))
    assert library_ask.time_window("what did I save in 2024", today) == (date(2024, 1, 1), date(2024, 12, 31))
    assert library_ask.time_window("transformers", today) is None


def test_owners_never_see_each_other(tmp_path, monkeypatch):
    owner = client_for(tmp_path, monkeypatch, "owner-1")
    item = save(owner, PAPER)["items"][0]
    project = owner.post("/library/lists", json={"kind": "project", "name": "Mine"}).json()
    other = client_for(tmp_path, monkeypatch, "owner-2")
    assert other.get("/library/items").json() == []
    assert other.patch(f"/library/items/{item['id']}", json={"status": "read"}).status_code == 404
    assert other.get(f"/library/lists/{project['id']}").status_code == 404
    assert other.post("/library/items", json={"papers": [OTHER], "list_id": project["id"]}).status_code == 404
    assert other.post("/library/notes", json={"body": "x", "item_id": item["id"]}).status_code == 404
    assert other.delete(f"/library/items/{item['id']}").status_code == 404
    assert other.post("/library/items/bulk", json={"ids": [item["id"]], "action": "delete"}).json() == {"updated": 0}
    assert len(owner.get("/library/items").json()) == 1


def test_anonymous_is_refused(tmp_path, monkeypatch):
    client = client_for(tmp_path, monkeypatch, "anonymous")
    assert client.get("/library/items").status_code == 401
