from __future__ import annotations

import uuid

import fitz
import pytest
from fastapi.testclient import TestClient

from app.api.deps import AuthContext, get_auth_context
from app.main import app
from app.services.comparison.uploads.repository import ComparisonPdfRepository


def make_pdf(label: str) -> bytes:
    document = fitz.open()
    page = document.new_page()
    page.insert_text(
        (50, 70),
        f"{label}\nAbstract\nIntroduction\nMethods\nDataset: CIFAR-10 with 50000 training images. "
        "We evaluated a transformer model using accuracy and F1 score. "
        "The proposed method achieves 91.2 percent accuracy and an F1 score of 0.89. "
        "The main limitation is high computational cost. We conclude that this method "
        "improves the benchmark results. " * 6,
        fontsize=10,
    )
    data = document.tobytes()
    document.close()
    return data


@pytest.fixture
def client(tmp_path, monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "database_url", f"sqlite:///{tmp_path / 'compare.db'}")
    monkeypatch.setattr(settings, "deployment_stage", "development")
    app.dependency_overrides[get_auth_context] = lambda: AuthContext(user_id="test-user", source="test", verified=True)
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def test_upload_rejects_non_pdf_bytes(client):
    result = client.post(
        "/api/v1/comparison/pdfs/upload",
        data={"comparison_id": str(uuid.uuid4())},
        files=[("files", ("fake.pdf", b"not a pdf", "application/pdf"))],
    )
    assert result.status_code == 415
    assert "valid PDF" in result.json()["detail"]


def test_upload_rejects_encrypted_pdf(client):
    document = fitz.open()
    page = document.new_page()
    page.insert_text((60, 70), "A password-protected paper with enough readable text.")
    data = document.tobytes(encryption=fitz.PDF_ENCRYPT_AES_256, owner_pw="owner", user_pw="secret")
    document.close()
    result = client.post(
        "/api/v1/comparison/pdfs/upload",
        data={"comparison_id": str(uuid.uuid4())},
        files=[("files", ("locked.pdf", data, "application/pdf"))],
    )
    assert result.status_code == 422
    assert "password" in result.json()["detail"].lower()


def test_uploaded_pdf_is_stored_and_comparison_uses_saved_pdf_text(client):
    comparison_id = str(uuid.uuid4())
    first = make_pdf("A full paper about image classification")
    second = make_pdf("A full paper about robust image classification")
    result = client.post(
        "/api/v1/comparison/pdfs/upload",
        data={"comparison_id": comparison_id},
        files=[("files", ("first.pdf", first, "application/pdf")), ("files", ("second.pdf", second, "application/pdf"))],
    )
    assert result.status_code == 200, result.text
    files = result.json()["files"]
    assert len(files) == 2
    assert files[0]["pages"] == 1
    assert "stored privately" in result.json()["stored_notice"]

    compared = client.post("/api/v1/comparison/pdfs/run", json={
        "comparison_id": comparison_id,
        "file_ids": [item["id"] for item in files],
        "focus": "image classification",
        "custom_columns": ["dataset", "method", "metric", "result", "limitation"],
    })
    assert compared.status_code == 200, compared.text
    payload = compared.json()
    ComparisonPdfRepository.load_papers(owner_id="test-user", comparison_id=comparison_id, file_ids=[item["id"] for item in files])
    assert payload["comparison_count"] == 2
    assert {row["title"] for row in payload["rows"]} == {"first", "second"}
    assert all(row["full_text_available"] for row in payload["rows"])
    assert any("page 1" in source.lower() for row in payload["rows"] for source in row["evidence_source"].values())
    assert len(payload["paper_profiles"]) == 2
    assert all(profile["profile_version"] == 2 for profile in payload["paper_profiles"])
    assert all(profile["reproducibility"]["code"]["status"] == "not stated" for profile in payload["paper_profiles"])
    insights = payload["insights_model"]
    assert insights["version"] == 1
    assert len(insights["takeaway"].split()) <= 25
    assert insights["head_to_head"] is None  # No split evidence was extracted from these PDFs.
    assert all(number["evidence"] for number in insights["key_numbers"])
    assert all(reference["paper_id"] in {row["paper_id"] for row in payload["rows"]} for number in insights["key_numbers"] for reference in number["evidence"])
    assert payload["insight_run_id"]
    cached = client.post("/api/v1/comparison/pdfs/run", json={
        "comparison_id": comparison_id,
        "file_ids": [item["id"] for item in files],
        "focus": "image classification",
        "custom_columns": ["dataset", "method", "metric", "result", "limitation"],
    })
    assert cached.status_code == 200, cached.text
    assert cached.json()["insight_run_id"] == payload["insight_run_id"]
    assert cached.json()["insights_cached"] is True
    assert cached.json()["insights_model"] == insights
    feedback = client.post(f"/api/v1/comparison/pdfs/insights/{payload['insight_run_id']}/feedback", json={"section_key": "study_design", "value": "useful"})
    assert feedback.status_code == 204
    saved_question = client.post(f"/api/v1/comparison/pdfs/{comparison_id}/insights/consensus_questions", json={"question": "Which papers report accuracy?", "result": {"papers": []}})
    assert saved_question.status_code == 200
    assert saved_question.json()["id"]

    pdf = client.get(f"/api/v1/comparison/pdfs/{files[0]['id']}")
    assert pdf.status_code == 200
    assert pdf.content.startswith(b"%PDF-")
    deleted = client.delete(f"/api/v1/comparison/pdfs/{files[0]['id']}")
    assert deleted.status_code == 204
    assert client.get(f"/api/v1/comparison/pdfs/{files[0]['id']}").status_code == 404


def test_upload_rejects_duplicate_pdf_in_one_comparison(client):
    comparison_id = str(uuid.uuid4())
    data = make_pdf("Duplicate paper content for a compare upload")
    result = client.post(
        "/api/v1/comparison/pdfs/upload",
        data={"comparison_id": comparison_id},
        files=[("files", ("one.pdf", data, "application/pdf"))],
    )
    assert result.status_code == 200
    duplicate = client.post(
        "/api/v1/comparison/pdfs/upload",
        data={"comparison_id": comparison_id},
        files=[("files", ("copy.pdf", data, "application/pdf"))],
    )
    assert duplicate.status_code == 409
    assert "already" in duplicate.json()["detail"]


def test_pdf_repository_is_owner_scoped(tmp_path, monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "database_url", f"sqlite:///{tmp_path / 'private.db'}")
    record = ComparisonPdfRepository.save(
        owner_id="owner-a",
        comparison_id=str(uuid.uuid4()),
        name="private.pdf",
        data=b"%PDF-1.4 test",
        page_count=1,
        text="private document",
        method="test",
    )
    assert ComparisonPdfRepository.read_pdf(owner_id="owner-b", file_id=record["id"]) is None
    with pytest.raises(PermissionError):
        ComparisonPdfRepository.load_papers(owner_id="owner-b", comparison_id=str(uuid.uuid4()), file_ids=[record["id"]])
