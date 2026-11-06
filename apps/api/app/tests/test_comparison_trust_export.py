import asyncio
from app.schemas.comparison import ComparisonRequest
from app.schemas.export import CitationExportRequest
from app.schemas.paper import PaperRecord
from app.schemas.trust import TrustAnalysisRequest
from app.schemas.workspace import WorkspaceCreateRequest
from app.services.comparison.engine import ComparisonEngine
from app.services.critique.trust import TrustAnalysisService
from app.services.exports.citations import CitationExportService
from app.services.workspace.rbac import WorkspaceService
from app.api.v1.endpoints import comparison as comparison_endpoint
from pydantic import ValidationError


def make_paper(**overrides) -> PaperRecord:
    data = {
        "paper_id": "p1",
        "title": "Hybrid Retrieval for Academic QA",
        "abstract": "We introduce a new benchmark dataset with n = 120 participants. Our hybrid RAG method outperforms dense retrieval and includes ablation analysis.",
        "year": 2024,
        "venue": "Journal of AI Systems",
        "doi": "10.1000/xyz123",
        "url": "https://example.org/p1",
        "pdf_url": "https://example.org/p1.pdf",
        "citation_count": 120,
        "reference_count": 40,
        "is_open_access": True,
        "authors": [{"name": "Alice"}, {"name": "Bob"}],
        "source": "openalex",
        "all_sources": ["openalex"],
        "external_ids": {"DOI": "10.1000/xyz123"},
    }
    data.update(overrides)
    return PaperRecord(**data)


def test_comparison_engine_builds_rows_and_markdown() -> None:
    engine = ComparisonEngine()
    source_text = "We introduce a new benchmark dataset with n = 120 participants. Our hybrid RAG method outperforms dense retrieval and includes ablation analysis."
    response = engine.compare(
        ComparisonRequest(
            papers=[
                make_paper(abstract=source_text),
                make_paper(
                    paper_id="p2",
                    title="Dense Retrieval Limitations",
                    abstract="This study highlights limitation patterns and reports underperforms behavior on the benchmark with n = 24 subjects.",
                    citation_count=12,
                    is_open_access=False,
                ),
            ],
            focus="retrieval",
            custom_columns=["dataset", "method", "sample size", "result", "limitation", "venue", "training dataset size"],
        )
    )
    assert len(response.rows) == 2
    assert response.comparison_count == 2
    assert response.max_supported_papers == 15
    assert "| Title | Year | Citations | OA | Similarity |" in response.export_markdown
    assert "Title,Year,Citations,OpenAccess,Similarity" in response.export_csv
    assert "\\begin{tabular}" in response.export_latex
    assert "\"paper_id\": \"p1\"" in response.export_json
    assert response.leaderboard[0] == "Hybrid Retrieval for Academic QA"
    assert response.grouped_methods
    assert response.similarity_heatmap
    assert response.heatmap_labels == [row.title for row in response.rows]
    assert response.best_paper_recommendation
    assert response.literature_review_section
    assert response.custom_columns_resolved == ["dataset", "method", "sample size", "result", "limitation", "venue", "training dataset size"]
    assert response.rows[0].extracted_columns["result"] != "Not found"
    result_quote = response.rows[0].evidence["result"]
    assert result_quote in source_text
    assert response.rows[0].confidence_by_column["result"] == "medium"
    assert response.rows[0].extracted_columns["training dataset size"] == "Not found"
    assert response.rows[0].confidence_by_column["training dataset size"] == "not_found"
    assert response.rows[0].citation in response.export_csv
    assert response.rows[0].citation in response.export_markdown
    fabricated_quote, _, fabricated_confidence = engine._evidence_for_column(
        "result", "Fabricated result", make_paper(abstract=source_text)
    )
    assert fabricated_quote == ""
    assert fabricated_confidence == "low"
    assert response.snapshot_metadata["comparison_count"] == 2
    assert response.auto_suggested_columns
    assert response.method_similarity_heatmap
    assert response.dataset_similarity_heatmap
    assert response.result_similarity_heatmap
    assert response.shareable_url.startswith("/comparison/share/")
    assert response.literature_review_export_job["status"] == "ready"


def test_comparison_engine_supports_more_than_ten_papers() -> None:
    engine = ComparisonEngine()
    papers = [
        make_paper(
            paper_id=f"bulk-{index}",
            title=f"Comparison Paper {index}",
            doi=f"10.1000/bulk-{index}",
            url=f"https://example.org/bulk-{index}",
            external_ids={"DOI": f"10.1000/bulk-{index}"},
            citation_count=150 - index,
            abstract=(
                f"We introduce benchmark dataset {index}. "
                f"Our method uses BM25 and RAG. "
                f"Results improve F1 for setting {index}. "
                f"Future work includes multilingual deployment."
            ),
        )
        for index in range(11)
    ]

    response = engine.compare(
        ComparisonRequest(
            papers=papers,
            focus="retrieval",
            custom_columns=["dataset", "method", "result"],
        )
    )

    assert response.comparison_count == 11
    assert len(response.rows) == 11
    assert len(response.timeline) == 11
    assert response.max_supported_papers >= 11
    assert response.snapshot_metadata["comparison_count"] == 11


def test_comparison_request_removes_duplicates_and_requires_two_unique_papers() -> None:
    paper = make_paper()
    request = ComparisonRequest(papers=[paper, make_paper(paper_id="p2"), paper])
    assert len(request.papers) == 2
    try:
        ComparisonRequest(papers=[paper, paper])
    except ValidationError:
        pass
    else:
        raise AssertionError("Duplicate-only comparison should be rejected")


def test_comparison_engine_supports_pinning_leaderboards_and_overlap_views() -> None:
    engine = ComparisonEngine()
    response = engine.compare(
        ComparisonRequest(
            papers=[
                make_paper(
                    paper_id="p1",
                    title="RAG on Shared Benchmark",
                    abstract="The RAG method reports F1 0.91 on Resora benchmark dataset with p < 0.05.",
                    citation_count=80,
                ),
                make_paper(
                    paper_id="p2",
                    title="BM25 on Shared Benchmark",
                    abstract="The BM25 method reports F1 0.72 on Resora benchmark dataset and highlights limitation.",
                    citation_count=150,
                ),
                make_paper(
                    paper_id="p3",
                    title="Transformer on Visual Corpus",
                    abstract="The transformer method reports AUC 0.88 on Visual corpus.",
                    citation_count=60,
                ),
            ],
            focus="F1 performance",
            custom_columns=["method", "dataset", "statistical significance"],
            pinned_paper_ids=["p1"],
            criterion="F1 performance",
        )
    )

    assert response.rows[0].paper_id == "p1"
    assert response.pinned_row_order == ["p1"]
    assert response.performance_leaderboard_by_dataset
    assert response.dataset_overlap_matrix
    assert response.citation_overlap_sets["highly_cited"]
    assert response.dendrogram_edges
    assert any(row.result_metrics for row in response.rows)


def test_comparison_uses_available_search_metadata_and_qualifies_missing_evidence() -> None:
    response = ComparisonEngine().compare(
        ComparisonRequest(
            papers=[
                make_paper(
                    paper_id="metadata-1",
                    abstract=None,
                    sample_size=240,
                    datasets=["OpenResearch Benchmark"],
                    methodologies=["Bayesian optimization"],
                    code_repositories=["https://github.com/example/project"],
                ),
                make_paper(paper_id="metadata-2", abstract="", datasets=["OpenResearch Benchmark"]),
            ],
            focus="Bayesian optimization",
            custom_columns=["method", "dataset", "dataset size", "code available", "year"],
        )
    )
    first = response.rows[0]
    assert first.abstract_available is False
    assert first.extracted_columns["method"] == "Bayesian optimization"
    assert first.extracted_columns["dataset"] == "OpenResearch Benchmark"
    assert first.extracted_columns["dataset size"] == "240"
    assert first.extracted_columns["code available"] == "https://github.com/example/project"
    assert first.evidence_source["dataset"] == "metadata"
    assert "available abstract and metadata" in response.narrative_summary
    assert "not proof of methodological equivalence" in response.narrative_summary


def test_comparison_extracts_values_and_quotes_from_supplied_full_paper_text() -> None:
    response = ComparisonEngine().compare(
        ComparisonRequest(
            papers=[
                make_paper(
                    paper_id="fulltext-1",
                    abstract="Short abstract without a method or score.",
                    full_text="We evaluate our RAG approach on the FullPaper Benchmark dataset. RAG achieves F1 0.94 and outperforms the dense baseline. Limitations remain for low-resource languages.",
                    full_text_status="provided",
                ),
                make_paper(
                    paper_id="fulltext-2",
                    abstract="Another short abstract.",
                    full_text="Dense retrieval is evaluated on the FullPaper Benchmark dataset with F1 0.78. The method fails to generalize to low-resource languages.",
                    full_text_status="provided",
                ),
            ],
            focus="retrieval performance",
            custom_columns=["method", "dataset", "metric", "result", "limitation"],
        )
    )
    first = response.rows[0]
    assert first.full_text_available is True
    assert first.extracted_columns["dataset"] == "FullPaper Benchmark"
    assert first.extracted_columns["result"].startswith("RAG achieves F1 0.94")
    assert first.evidence_source["result"] == "full paper text"
    assert "Full-text coverage for retrieval performance: 2 of 2" in response.narrative_summary


def test_comparison_rejects_aim_as_result_and_future_work_as_limitation() -> None:
    engine = ComparisonEngine()
    text = (
        "This study aims to improve accuracy in mobile detection. "
        "Future work will investigate larger benchmarks. "
        "The model achieved 96.2% accuracy on Celeb-DF. "
        "Performance is limited by low-light videos."
    )
    assert engine._extract_result_signal(text).startswith("The model achieved 96.2% accuracy")
    assert engine._extract_limitation_signal(text) == "Performance is limited by low-light videos."


def test_comparison_searches_results_and_limitations_sections_first() -> None:
    engine = ComparisonEngine()
    paper = make_paper(
        abstract="We aim to improve accuracy.",
        full_text=(
            "Abstract\nWe propose a new model.\n"
            "1 Introduction\nThis study aims to improve accuracy by 10%.\n"
            "4 Experiments\nWe evaluate the proposed model.\n"
            "5 Results\nThe model achieves 94.2% accuracy on the FaceForensics++ test set.\n"
            "6 Limitations\nThe model is limited by poor performance on compressed videos."
        ),
    )
    result = engine._extract_column_value("result", paper)
    limitation = engine._extract_column_value("limitation", paper)
    assert result.startswith("The model achieves 94.2% accuracy")
    assert limitation.startswith("The model is limited by poor performance")


def test_full_text_comparison_keeps_unlabeled_body_and_marks_conceptual_papers() -> None:
    engine = ComparisonEngine()
    full_text = (
        "Abstract\nWe summarize the fundamentals and provide a conceptual distinction between key ideas.\n"
        "Introduction\nContext for the paper.\n"
        "Conceptual distinction\nThe unnumbered body describes the conceptual synthesis in detail.\n"
        "Conclusion\nThe concepts are summarized."
    )
    assert "unnumbered body" in engine._text_with_preferred_sections(full_text, ("results", "discussion"))
    response = engine.compare(ComparisonRequest(
        papers=[
            make_paper(paper_id="concept", abstract="We summarize the fundamentals and provide a conceptual distinction between key ideas.", full_text=full_text),
            make_paper(paper_id="control", title="Control study", abstract="A separate study with no matching evidence."),
        ],
        custom_columns=["method", "dataset", "result", "sample size"],
    ))
    conceptual = next(row for row in response.rows if row.paper_id == "concept")
    assert conceptual.document_type == "conceptual_article"
    assert conceptual.extracted_columns["method"] == "Conceptual synthesis"
    assert conceptual.extracted_columns["dataset"] == "Not applicable: conceptual article"
    assert conceptual.extracted_columns["result"] == "Conceptual overview; no original experiment reported"
    assert not conceptual.methods or conceptual.methods == ["Conceptual synthesis"]
    assert not conceptual.datasets


def test_result_metrics_are_taken_from_results_sections_and_normalized() -> None:
    engine = ComparisonEngine()
    text = (
        "Introduction\nPrior work reports 81% accuracy.\n"
        "Results\nThe proposed model reaches 94.2% accuracy and F1-score of 0.91. "
        "RMSE was 2.4 on the test set."
    )
    metrics = engine._extract_result_metrics(text)
    assert abs(metrics["ACCURACY"] - 0.942) < 1e-9
    assert metrics["F1"] == 0.91
    assert metrics["RMSE"] == 2.4


def test_comparison_does_not_emit_search_placeholders_and_marks_books_not_applicable() -> None:
    response = ComparisonEngine().compare(
        ComparisonRequest(
            papers=[
                make_paper(paper_id="book", venue="MIT Press eBooks", publication_type="book", abstract=None, methodologies=["General Research"], datasets=["Unspecified Dataset"]),
                make_paper(paper_id="article", publication_type="journal-article", abstract="A paper with no experiment details."),
            ],
            focus="general",
            custom_columns=["method", "dataset", "result"],
        )
    )
    book = response.rows[0]
    assert book.document_type == "book"
    assert book.extracted_columns["method"] == "Not applicable: book"
    assert book.extracted_columns["dataset"] == "Not applicable: book"
    assert "General Research" not in str(book.model_dump())
    assert "Unspecified Dataset" not in str(book.model_dump())


def test_compare_pdf_loader_uses_existing_pdf_extractor(monkeypatch) -> None:
    from types import SimpleNamespace

    async def fake_extract(**_kwargs):
        return SimpleNamespace(status="ok", extraction_method="pymupdf", extracted_text="Hybrid Retrieval for Academic QA. Full paper evidence. " * 80)

    monkeypatch.setattr(comparison_endpoint, "_public_https_url", lambda _url: True)
    monkeypatch.setattr(comparison_endpoint.document_extractor, "extract", fake_extract)
    paper = make_paper(paper_id="pdf-loaded", pdf_url="https://papers.example.org/full.pdf")
    enriched = asyncio.run(comparison_endpoint._load_full_text(paper))
    assert enriched.full_text_status == "extracted"
    assert enriched.full_text.startswith("Full paper evidence.")


def test_compare_pdf_loader_reads_publisher_link_without_oa_flag(monkeypatch) -> None:
    from types import SimpleNamespace

    async def fake_extract(*, source_url):
        assert source_url == "https://link.springer.com/content/pdf/10.1007/example.pdf"
        return SimpleNamespace(
            status="ok",
            extraction_method="pymupdf",
            extracted_text="Hybrid Retrieval for Academic QA. Full paper evidence. " * 80,
            normalized_source_url=source_url,
        )

    monkeypatch.setattr(comparison_endpoint, "_public_https_url", lambda _url: True)
    monkeypatch.setattr(comparison_endpoint.document_extractor, "extract", fake_extract)
    paper = make_paper(
        paper_id="publisher-link",
        is_open_access=False,
        pdf_url="https://link.springer.com/content/pdf/10.1007/example.pdf",
        pdf_urls=[],
    )
    enriched = asyncio.run(comparison_endpoint._load_full_text(paper))
    assert enriched.full_text_status == "extracted"
    assert enriched.full_text_source == "link.springer.com"
    assert enriched.full_text_source_url == "https://link.springer.com/content/pdf/10.1007/example.pdf"


def test_compare_pdf_loader_tries_other_open_locations(monkeypatch) -> None:
    from types import SimpleNamespace

    calls = []
    async def fake_extract(*, source_url):
        calls.append(source_url)
        if source_url.endswith("/first.pdf"):
            return SimpleNamespace(status="error", extraction_method="download-error", extracted_text="")
        return SimpleNamespace(status="ok", extraction_method="pymupdf", extracted_text="Hybrid Retrieval for Academic QA. Verified text. " * 80)

    monkeypatch.setattr(comparison_endpoint, "_public_https_url", lambda _url: True)
    monkeypatch.setattr(comparison_endpoint.document_extractor, "extract", fake_extract)
    paper = make_paper(
        paper_id="multiple-locations",
        pdf_url="https://first.example/first.pdf",
        pdf_urls=["https://second.example/paper.pdf"],
    )
    enriched = asyncio.run(comparison_endpoint._load_full_text(paper))
    assert calls == ["https://first.example/first.pdf", "https://second.example/paper.pdf"]
    assert enriched.full_text_status == "extracted"
    assert enriched.full_text_source == "second.example"


def test_trust_analysis_scores_evidence() -> None:
    service = TrustAnalysisService()
    response = service.analyze(
        TrustAnalysisRequest(
            paper=make_paper(),
            peer_reviewed=True,
            citation_contexts=["This result supports prior work.", "However, unlike earlier findings, performance drops on noisy data."],
            related_papers=[
                make_paper(
                    paper_id="p3",
                    title="Noisy Data Limitation Study",
                    abstract="This study highlights limitation patterns and underperforms on the benchmark.",
                    authors=[{"name": "Alice"}],
                )
            ],
        )
    )
    assert response.trust_score >= 6
    assert response.evidence_strength in {"medium", "high"}
    assert response.green_flags
    assert response.methodology_quality_checklist
    assert response.citation_context_labels
    assert response.trust_score_changelog
    assert response.score_trace["final_trust"] >= response.score_trace["base_trust"]
    assert any(entry.evidence for entry in response.trust_score_changelog)
    assert any(signal.evidence for signal in response.signals)
    assert response.contradiction_details
    assert response.contradiction_details[0].supporting_evidence
    assert response.retraction_check == "no_retraction_signal"
    assert response.funding_transparency_flag in {"disclosed", "not_obvious"}
    assert response.author_track_record_summary
    assert response.journal_impact_profile.impact_tier
    assert response.sample_size_profile.adequacy
    assert response.bias_tag_details
    assert response.statistical_sanity_checks
    assert response.evidence_meter


def test_trust_analysis_tracks_negative_signals_and_flagged_moderation() -> None:
    service = TrustAnalysisService()
    response = service.analyze(
        TrustAnalysisRequest(
            paper=make_paper(
                paper_id="risk-1",
                title="State-of-the-Art Guarantee Paper",
                abstract="We always guarantee state-of-the-art results with n = 12 samples. This study has limitation statements but underperforms on noisy data.",
                citation_count=0,
                is_open_access=False,
            ),
            peer_reviewed=False,
            citation_contexts=["However, contrary to earlier findings, performance drops."],
            related_papers=[
                make_paper(
                    paper_id="risk-2",
                    title="Noisy Benchmark Weaknesses",
                    abstract="This study highlights limitation patterns and underperforms on the benchmark.",
                    authors=[{"name": "Alice"}],
                )
            ],
        )
    )

    assert response.moderation_status == "flagged"
    assert "Potential overclaiming language" in response.red_flags
    assert response.score_trace["final_trust"] <= response.score_trace["base_trust"]
    assert any(label.label == "dispute" for label in response.citation_context_labels)
    assert response.outlier_anomaly_flags
    assert response.moderation_queue_entry is not None
    assert response.moderation_queue_entry.reason
    assert response.self_citation_flag in {"low", "moderate", "high"}


def test_trust_analysis_supports_manual_flag_queue_entry() -> None:
    service = TrustAnalysisService()
    response = service.analyze(
        TrustAnalysisRequest(
            paper=make_paper(
                paper_id="manual-1",
                title="Questionable Benchmark Claim",
                abstract="We report strong results and mention a correction notice. Conflict of interest is declared.",
                citation_count=10,
                is_open_access=True,
            ),
            manual_flag_as_questionable=True,
            moderation_note="Needs supervisor review before citation.",
            related_papers=[make_paper(paper_id="manual-2", authors=[{"name": "Alice"}])],
        )
    )

    assert response.moderation_queue_entry is not None
    assert response.moderation_queue_entry.status == "queued_for_review"
    assert response.moderation_queue_entry.note == "Needs supervisor review before citation."
    assert response.erratum_check == "erratum_or_correction_mentioned"
    assert response.conflict_of_interest_flag == "declared"


def test_citation_export_service_formats_bibtex() -> None:
    service = CitationExportService()
    response = service.export(CitationExportRequest(papers=[make_paper()], format="bibtex"))
    assert "@article{" in response.content
    assert response.item_count == 1


def test_workspace_service_returns_members() -> None:
    workspace = WorkspaceService().get_workspace("default-lab")
    assert workspace.members
    assert "manage" in workspace.permissions
    assert "guest-links" in workspace.share_capabilities
    assert workspace.activity_summary["drafts"] == 5
    assert workspace.role_matrix["owner"]
    assert workspace.notification_channels
    assert workspace.template_origin == "default-research-lab"


def test_workspace_service_can_create_review_ready_workspace() -> None:
    service = WorkspaceService()
    created = service.create_workspace(
        WorkspaceCreateRequest(
            name="Global Research Team",
            owner_email="owner@example.org",
            template_origin="thesis-lab",
            review_mode="supervisor-review",
            member_emails=["editor1@example.org", "editor2@example.org"],
            notification_channels=["email", "discord"],
            shared_folders=["Core Papers", "Methods", "Supervisor Notes"],
        )
    )
    assert created.workspace_id.startswith("ws-")
    assert created.default_review_mode == "supervisor-review"
    assert created.template_origin == "thesis-lab"
    assert len(created.members) == 3
    assert "research-archives" in created.share_capabilities
    assert "usage-monitor" in created.dashboards
