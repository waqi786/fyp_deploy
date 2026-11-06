import asyncio
import base64

import httpx
import pytest

from app.schemas.document import (
    ExtractedFigure,
    FigureComparisonRequest,
    FigureQuestionRequest,
    LibraryImageSearchRequest,
)
from app.schemas.paper import PaperRecord
from app.services.documents.image_analysis import FigureImageAnalysisService
from app.services.documents.multimodal_workbench import MultimodalWorkbenchService
from app.services.documents.pdf_extraction import DocumentExtractionService
from app.services.storage.background_cache import BackgroundPaperCache
from app.services.writing.draft_generation import DraftGenerationService


def make_paper() -> PaperRecord:
    return PaperRecord(
        paper_id="paper-1",
        title="Hybrid Retrieval Study",
        abstract="This paper introduces a benchmark. Figure 1: Accuracy improves over time. E = mc^2. References should be removed.",
        year=2024,
        venue="AI Journal",
        doi="10.1000/test",
        url="https://example.org/paper-1",
        pdf_url="https://example.org/paper-1.pdf",
        citation_count=5,
        reference_count=12,
        is_open_access=True,
        authors=[{"name": "Alice"}],
        source="openalex",
    )


def test_document_extraction_from_text_strips_references_and_detects_equations() -> None:
    service = DocumentExtractionService()
    response = asyncio.run(
        service.extract(
            raw_text="Introduction text. Figure 1: Accuracy across epochs. Table 1: Benchmark metrics.\nMetric|Value\nF1|0.87\nAUC|0.91\nE = mc^2. References Smith et al."
        )
    )
    assert response.status == "ok"
    assert response.detected_equations
    assert response.equation_explanations
    assert response.figures
    assert response.tables
    assert response.figures[0].alt_text
    assert response.tables[0].headers == ["Metric", "Value"]
    assert response.tables[0].rows[0] == ["F1", "0.87"]
    assert "References" not in response.extracted_text
    assert response.table_csv_exports
    assert response.figure_caption_cross_references
    assert response.accessibility_alt_text
    assert response.dependency_diagnostics
    assert response.editable_extracted_text
    assert isinstance(response.manual_verification_required, bool)
    assert isinstance(response.extraction_quality_flags, list)
    assert response.layout_reconstruction["columns_detected"] >= 1
    assert response.table_of_contents


def test_document_extraction_surfaces_multimodal_production_signals() -> None:
    service = DocumentExtractionService()
    response = asyncio.run(
        service.extract(
            raw_text=(
                "Contents\nIntroduction 1\nMethods 2\nResults 3\nIntroduction. "
                "Figure 1: Accuracy curve 95 96 97 with no baseline. As shown in Figure 1, accuracy improves. "
                "Table 1: Benchmark metrics.\nMetric|Value\nF1|0.87\nAUC|0.91\n"
                "Equation y = mx + b explains the line. Handwritten margin note says check axis. "
                "Supplementary material: https://zenodo.org/record/supplementary"
            )
        )
    )
    assert response.suspicious_chart_design_flags
    assert response.handwritten_annotations
    assert response.supplementary_material_links
    assert response.equation_explanations[0].interactive_variables
    assert response.figures[0].library_index_terms


def test_figure_image_analysis_extracts_upload_query_metadata() -> None:
    png_header = (
        b"\x89PNG\r\n\x1a\n"
        b"\x00\x00\x00\rIHDR"
        b"\x00\x00\x00\x10"
        b"\x00\x00\x00\x08"
        b"\x08\x02\x00\x00\x00"
        b"\x00\x00\x00\x00"
    )
    response = FigureImageAnalysisService().analyze(
        filename="accuracy-curve.png",
        content_type="image/png",
        data=png_header + b"\xff" * 64,
    )
    assert response.width == 16
    assert response.height == 8
    assert response.diagram_type == "chart"
    assert "accuracy curve" in response.search_caption
    assert response.perceptual_hash


def test_document_extraction_blocks_known_domains() -> None:
    service = DocumentExtractionService()
    response = asyncio.run(service.extract(source_url="https://www.researchgate.net/publication/123"))
    assert response.status == "blocked"
    assert response.blocked_reason == "BLOCKED_DOMAIN"


def test_document_extraction_blocks_authwall_like_urls() -> None:
    service = DocumentExtractionService()
    response = asyncio.run(service.extract(source_url="https://example.org/login?captcha=true"))
    assert response.status == "blocked"
    assert response.blocked_reason == "CAPTCHA_OR_AUTHWALL"


def test_document_extraction_byte_decode_path() -> None:
    service = DocumentExtractionService()
    payload = base64.b64encode(b"Figure 2: Benchmark comparison. x = y + z. This byte payload is long enough to be parsed safely.").decode("utf-8")
    response = asyncio.run(service.extract(raw_bytes_base64=payload))
    assert response.status == "ok"
    assert response.extraction_method in {"byte-decode", "ocr-fallback"}
    assert response.processing_notes


def test_document_extraction_uses_pymupdf_for_real_pdf_bytes() -> None:
    fitz = pytest.importorskip("fitz")
    document = fitz.open()
    page = document.new_page()
    page.insert_text((72, 72), "Introduction. Figure 1: Production PDF extraction quality. score = bm25 + dense.")
    payload = base64.b64encode(document.tobytes()).decode("utf-8")

    response = asyncio.run(DocumentExtractionService().extract(raw_bytes_base64=payload))

    assert response.status == "ok"
    assert response.extraction_method == "pymupdf"
    assert response.dependency_diagnostics["pymupdf_available"] is True
    assert "Production PDF extraction" in response.extracted_text


def test_document_extraction_reads_plain_text_from_html_pages() -> None:
    service = DocumentExtractionService()
    html = (
        "<html><body><article><h1>Diabetes prediction using BRFSS</h1>"
        "<p>This study evaluates diabetes prediction using BRFSS survey records, logistic regression, random forests, "
        "and feature selection across patient risk factors.</p>"
        "<p>Results report improved F1 and AUC while limitations include self-reported health data and survey bias.</p>"
        "</article></body></html>"
    )
    response = service._extract_from_http_response(
        httpx.Response(200, content=html.encode("utf-8"), headers={"content-type": "text/html; charset=utf-8"})
    )

    assert response is not None
    assert response.extraction_method == "html-page"
    assert "Diabetes prediction using BRFSS" in response.extracted_text


def test_document_extraction_ocr_fallback_marks_scanned_like_payloads() -> None:
    service = DocumentExtractionService()
    scanned_like = base64.b64encode(b"F1gur3 3 Accur4cy curv3 ov3r 3p0chs x = y + z sc4nned p4yload t3xt with nois3").decode("utf-8")
    response = asyncio.run(service.extract(raw_bytes_base64=scanned_like))
    assert response.status == "ok"
    assert response.extraction_method == "ocr-fallback"
    assert response.scanned_pdf_detected is True
    assert response.ocr_confidence is not None
    assert response.layout_reconstruction["deskew_applied"] is True
    assert response.layout_reconstruction["contrast_enhanced"] is True


def test_multimodal_workbench_answers_compares_and_searches_figures() -> None:
    extracted = asyncio.run(
        DocumentExtractionService().extract(
            raw_text="Figure 1: Accuracy curve over epochs 80 90 95. Figure 2: Architecture pipeline with encoder and decoder."
        )
    )
    service = MultimodalWorkbenchService()
    qa = service.answer_visual_question(
        FigureQuestionRequest(
            question="What does Figure 1 show?",
            figures=extracted.figures,
            tables=extracted.tables,
            equations=extracted.equation_explanations,
        )
    )
    comparison = service.compare_figures(FigureComparisonRequest(figures=extracted.figures))
    search = service.search_library_images(LibraryImageSearchRequest(query="accuracy curve", figures=extracted.figures))
    assert qa.cited_visual_ids == ["fig-1"]
    assert comparison.comparison_matrix
    assert search.matches


def test_document_extraction_normalizes_arxiv_urls() -> None:
    service = DocumentExtractionService()
    normalized = service._normalize_source_url("https://arxiv.org/abs/2401.12345")
    assert normalized == "https://export.arxiv.org/pdf/2401.12345"


def test_draft_generation_counts_figures_and_runs_self_critique() -> None:
    service = DraftGenerationService()
    response = service.generate(
        title="Hybrid Retrieval Study",
        extracted_text="This paper studies retrieval. It uses BM25 and dense fusion. Results improve grounding. Conclusion supports deployment.",
        figures=[
            ExtractedFigure(
                figure_id="f1",
                caption="Figure 1: Accuracy curve on benchmark",
                chart_type="figure",
                description="Benchmark figure",
                data_insights=[],
            )
        ],
        target_style="ieee",
        language="en",
    )
    assert response.figure_analysis_count == 1
    assert response.sections["introduction"].startswith("In IEEE style")
    assert "supported_claims" in response.self_critique
    assert response.confidence_score > 0
    assert response.source_spans
    assert response.generated_at


def test_draft_generation_urdu_mode_does_not_emit_placeholder_text() -> None:
    service = DraftGenerationService()
    response = service.generate(
        title="Urdu Research Support",
        extracted_text="This paper studies Urdu retrieval. It reports results and limitations for scanned PDFs.",
        figures=[],
        target_style="apa",
        language="ur",
    )
    joined = " ".join(response.sections.values())
    assert "placeholder" not in joined.lower()
    assert "خلاصہ" in response.sections["abstract"]
    assert "ماخذ" in joined


def test_background_cache_batches_and_returns_fresh_paper() -> None:
    cache = BackgroundPaperCache()
    result = asyncio.run(cache.store_papers_background([make_paper()]))
    assert result.total_items == 1
    assert cache.get_fresh("paper-1") is not None
