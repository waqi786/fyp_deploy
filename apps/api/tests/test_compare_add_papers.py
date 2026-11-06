"""Compare: papers added from Search/Reader are stored exactly like uploads; missing PDFs are reported, never faked.

No network: the open-access download is replaced by a local PDF.
"""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.deps import AuthContext, get_auth_context
from app.api.v1.endpoints import comparison
from app.core.config import settings
from app.services.reader import fetch

fitz = pytest.importorskip("fitz")  # Compare validates PDFs with the same library as uploads


def paper_pdf(title: str) -> bytes:
    document = fitz.open()
    page = document.new_page()
    body = (
        f"{title}\n\nAbstract. We propose a decoding method and evaluate it on the POPE benchmark. "
        "Accuracy improves from 83.9 to 86.9 percent compared with the greedy baseline. "
        "The method needs no training and code is available on GitHub. Limitations: only English captions are tested. "
    ) * 3
    page.insert_textbox(fitz.Rect(50, 50, 550, 800), body, fontsize=10)
    data = document.tobytes()
    document.close()
    return data


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "database_url", f"sqlite:///{tmp_path / 'compare.sqlite3'}")
    app = FastAPI()
    app.include_router(comparison.router, prefix="/comparison")
    app.dependency_overrides[get_auth_context] = lambda: AuthContext(user_id="owner-1", source="test", verified=True)

    async def no_discovery(_paper):
        return []

    monkeypatch.setattr(comparison, "_openalex_oa_locations", no_discovery)
    monkeypatch.setattr(comparison, "_unpaywall_locations", no_discovery)
    return TestClient(app)


def test_open_access_papers_are_stored_and_missing_ones_are_reported(client, monkeypatch):
    pdfs = {"https://example.org/a.pdf": paper_pdf("Grounded Decoding Reduces Hallucination")}

    async def fake_download(url, **_):
        if url in pdfs:
            return pdfs[url]
        raise fetch.FetchFailed("no pdf")

    monkeypatch.setattr(fetch, "download_pdf", fake_download)
    response = client.post("/comparison/pdfs/add-papers", json={"papers": [
        {"key": "p1", "title": "Grounded Decoding Reduces Hallucination", "pdf_url": "https://example.org/a.pdf"},
        {"key": "p2", "title": "A paper without a free PDF", "doi": "10.1000/closed"},
    ]})
    assert response.status_code == 200
    body = response.json()
    assert len(body["files"]) == 1 and body["files"][0]["pages"] == 1
    assert body["unavailable"] == [{"key": "p2", "title": "A paper without a free PDF", "reason": "no_open_pdf", "publisher_url": "https://doi.org/10.1000/closed"}]

    # Stored like an upload: it can be listed and compared with the normal endpoints.
    listed = client.get("/comparison/pdfs", params={"comparison_id": body["comparison_id"]}).json()["files"]
    assert [item["id"] for item in listed] == [body["files"][0]["id"]]


def test_a_pdf_for_a_different_paper_is_rejected(client, monkeypatch):
    async def wrong_pdf(url, **_):
        return paper_pdf("Completely Unrelated Study Of Soil Bacteria")

    monkeypatch.setattr(fetch, "download_pdf", wrong_pdf)
    body = client.post("/comparison/pdfs/add-papers", json={"papers": [
        {"key": "p1", "title": "Grounded Decoding Reduces Hallucination In Vision Language Models", "pdf_url": "https://example.org/x.pdf"},
    ]}).json()
    assert body["files"] == [] and body["unavailable"][0]["reason"] == "mismatch"


def test_adding_the_same_pdf_twice_is_a_duplicate_not_an_error(client, monkeypatch):
    data = paper_pdf("Grounded Decoding Reduces Hallucination")

    async def same(url, **_):
        return data

    monkeypatch.setattr(fetch, "download_pdf", same)
    first = client.post("/comparison/pdfs/add-papers", json={"papers": [{"key": "a", "title": "Grounded Decoding Reduces Hallucination", "pdf_url": "https://example.org/a.pdf"}]}).json()
    second = client.post("/comparison/pdfs/add-papers", json={"comparison_id": first["comparison_id"], "papers": [{"key": "b", "title": "Grounded Decoding Reduces Hallucination", "pdf_url": "https://example.org/a.pdf"}]}).json()
    assert second["files"] == [] and second["unavailable"][0]["reason"] == "duplicate"


def test_uploads_still_behave_as_before(client):
    data = paper_pdf("Grounded Decoding Reduces Hallucination")
    ok = client.post("/comparison/pdfs/upload", files=[("files", ("a.pdf", data, "application/pdf"))])
    assert ok.status_code == 200 and ok.json()["files"][0]["pages"] == 1
    not_pdf = client.post("/comparison/pdfs/upload", files=[("files", ("a.pdf", b"hello", "application/pdf"))])
    assert not_pdf.status_code == 415 and "not a valid PDF" in not_pdf.json()["detail"]
