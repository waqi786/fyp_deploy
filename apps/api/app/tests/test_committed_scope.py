from app.schemas.search import SearchRequest
from app.services.search.source_ids import DEFAULT_SCHOLARLY_SOURCES
from app.services.verification.reports import VerificationReportService


def test_committed_scope_matrix_covers_all_prompt_items() -> None:
    response = VerificationReportService().build_committed_scope()
    by_number = {item.item_number: item for item in response.items}

    assert response.project == "Resora"
    assert response.source_document.startswith("CODEX BUILD PROMPT")
    assert len(response.items) == 22
    assert response.done_count > 0
    assert response.partial_count > 0
    assert response.blocked_count == 0
    assert by_number[1].title.startswith("Multi-source search")
    assert by_number[7].status_label == "âœ… DONE"
    assert by_number[20].status_label.startswith("âš ï¸")
    assert all(item.evidence and item.verification_command and item.unhappy_path for item in response.items)


def test_committed_scope_default_search_uses_configured_research_sources() -> None:
    request = SearchRequest(query="hybrid retrieval")

    assert request.sources == DEFAULT_SCHOLARLY_SOURCES
    assert len(request.sources) == len(set(request.sources))

def test_committed_scope_surfaces_out_of_scope_guardrails() -> None:
    response = VerificationReportService().build_committed_scope()
    guardrail_text = " ".join(item.rule + " " + item.evidence for item in response.guardrails).lower()
    out_of_scope_text = " ".join(response.out_of_scope_items).lower()

    assert "configured scholarly source set" in guardrail_text
    assert "safe fallback" in guardrail_text
    assert "plagiarism" in out_of_scope_text
    assert "zotero/mendeley" in out_of_scope_text

