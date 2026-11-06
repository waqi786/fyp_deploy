"""Compare: saved comparisons (list, rename, delete with PDFs) and private translation of table values.

No network: PDFs are built locally and the translator is replaced by a fake.
"""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.deps import AuthContext, get_auth_context
from app.api.v1.endpoints import comparison
from app.core.config import settings
from app.services.search import translation

fitz = pytest.importorskip("fitz")


def pdf(title: str) -> bytes:
    document = fitz.open()
    page = document.new_page()
    page.insert_textbox(fitz.Rect(50, 50, 550, 800), f"{title}\n\nAbstract. We evaluate a decoding method on the POPE benchmark. " * 4, fontsize=10)
    data = document.tobytes()
    document.close()
    return data


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


def make_client(tmp_path, monkeypatch, user="owner-1"):
    import app.services.credits.service as credit_service

    monkeypatch.setattr(credit_service, "get_credit_service", lambda: FakeCredits())
    monkeypatch.setattr(settings, "database_url", f"sqlite:///{tmp_path / 'compare.sqlite3'}")
    app = FastAPI()
    app.include_router(comparison.router, prefix="/comparison")
    app.dependency_overrides[get_auth_context] = lambda: AuthContext(user_id=user, source="test", verified=True)
    return TestClient(app)


def upload(client, *titles):
    response = client.post("/comparison/pdfs/upload", files=[("files", (f"{title}.pdf", pdf(title), "application/pdf")) for title in titles])
    assert response.status_code == 200, response.text
    return response.json()["comparison_id"]


def test_saved_list_rename_and_delete(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    comparison_id = upload(client, "Grounded Decoding Paper", "Contrastive Decoding Paper")

    listed = client.get("/comparison/pdfs/saved").json()["comparisons"]
    assert [item["comparison_id"] for item in listed] == [comparison_id]
    assert listed[0]["file_count"] == 2 and listed[0]["name"]  # unnamed comparisons are still listed

    first = client.put(f"/comparison/pdfs/saved/{comparison_id}", json={"default_name": "Hallucination decoding", "focus": "decoding", "columns": ["method", "result"]}).json()
    assert first["name"] == "Hallucination decoding" and first["columns"] == ["method", "result"]
    # A later run must not overwrite a name the owner chose.
    client.put(f"/comparison/pdfs/saved/{comparison_id}", json={"name": "My review"})
    again = client.put(f"/comparison/pdfs/saved/{comparison_id}", json={"default_name": "Something else", "focus": "decoding v2"}).json()
    assert again["name"] == "My review" and again["focus"] == "decoding v2" and again["columns"] == ["method", "result"]

    assert client.put(f"/comparison/pdfs/saved/{comparison_id}", json={"name": "   "}).status_code == 422
    assert client.put("/comparison/pdfs/saved/not-a-uuid", json={"name": "x"}).status_code == 400

    assert client.delete(f"/comparison/pdfs/saved/{comparison_id}").status_code == 204
    assert client.get("/comparison/pdfs/saved").json()["comparisons"] == []
    assert client.get("/comparison/pdfs", params={"comparison_id": comparison_id}).json()["files"] == []


def test_saved_comparisons_are_private_to_their_owner(tmp_path, monkeypatch):
    owner = make_client(tmp_path, monkeypatch, "owner-1")
    comparison_id = upload(owner, "Private Paper One", "Private Paper Two")
    other = make_client(tmp_path, monkeypatch, "owner-2")
    assert other.get("/comparison/pdfs/saved").json()["comparisons"] == []
    assert other.put(f"/comparison/pdfs/saved/{comparison_id}", json={"name": "stolen"}).status_code == 404
    other.delete(f"/comparison/pdfs/saved/{comparison_id}")
    assert len(owner.get("/comparison/pdfs", params={"comparison_id": comparison_id}).json()["files"]) == 2


def test_translate_is_private_cached_and_charged_once(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    comparison_id = upload(client, "Grounded Decoding Paper", "Contrastive Decoding Paper")
    calls = []

    def fake(segments, language, *, source_language="auto", user_content=True, **_):
        calls.append((list(segments), language, user_content))
        return [f"[{language}] {item}" for item in segments]

    monkeypatch.setattr(translation, "translate_batch", fake)
    comparison._TRANSLATION_CACHE.clear()
    body = client.post(f"/comparison/pdfs/{comparison_id}/translate", json={"language": "ur", "texts": ["Contrastive decoding", "POPE", "Contrastive decoding"]}).json()
    assert body["translations"] == ["[ur] Contrastive decoding", "[ur] POPE", "[ur] Contrastive decoding"]
    assert calls == [(["Contrastive decoding", "POPE"], "ur", True)]  # duplicates sent once, as private content
    assert body["credits_used"] >= 1
    cached = client.post(f"/comparison/pdfs/{comparison_id}/translate", json={"language": "ur", "texts": ["POPE"]}).json()
    assert cached == {"translations": ["[ur] POPE"], "credits_used": 0} and len(calls) == 1


def test_translate_failures_and_limits(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    comparison_id = upload(client, "Grounded Decoding Paper", "Contrastive Decoding Paper")
    comparison._TRANSLATION_CACHE.clear()

    def broken(*_args, **_kwargs):
        raise RuntimeError("provider down")

    monkeypatch.setattr(translation, "translate_batch", broken)
    failed = client.post(f"/comparison/pdfs/{comparison_id}/translate", json={"language": "ur", "texts": ["Method"]})
    assert failed.status_code == 503 and failed.json()["detail"]["code"] == "translation_unavailable"
    assert client.post(f"/comparison/pdfs/{comparison_id}/translate", json={"language": "ur", "texts": ["x" * 2001]}).status_code == 413
    assert client.post(f"/comparison/pdfs/{comparison_id}/translate", json={"language": "ur;drop", "texts": ["a"]}).status_code == 422
    assert client.post("/comparison/pdfs/2f1c9a3e-0000-4000-8000-000000000000/translate", json={"language": "ur", "texts": ["a"]}).status_code == 404
