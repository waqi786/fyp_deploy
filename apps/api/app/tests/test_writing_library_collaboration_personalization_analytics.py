from pathlib import Path
import zipfile

from app.schemas.analytics import AnalyticsRequest
from app.schemas.collaboration import CollaborationRequest, CommentThread, WorkspaceTask
from app.schemas.document import ExtractedFigure, ExtractedTable
from app.schemas.library import CitationImportRequest, CitationLibraryRequest, CitationPreviewRequest
from app.schemas.paper import PaperRecord
from app.schemas.personalization import PersonalizationRequest
from app.schemas.writing import LiteratureReviewRequest
from app.services.analytics.dashboard import AnalyticsService
from app.services.library.manager import CitationLibraryService
from app.services.personalization.profile import PersonalizationService
from app.services.workspace.collaboration import CollaborationService
from app.services.writing.literature_review import LiteratureReviewService


def make_paper(**overrides) -> PaperRecord:
    data = {
        "paper_id": "w1",
        "title": "Hybrid Retrieval Benchmark Dataset",
        "abstract": "This dataset benchmark compares multimodal retrieval, reports benchmark scores, and discusses future work.",
        "year": 2025,
        "venue": "Journal of AI Systems",
        "doi": "10.1000/resora.1",
        "url": "https://example.org/w1",
        "pdf_url": "https://example.org/w1.pdf",
        "citation_count": 55,
        "reference_count": 21,
        "is_open_access": True,
        "authors": [{"name": "Ali Khan"}, {"name": "Sara Noor"}],
        "source": "openalex",
    }
    data.update(overrides)
    return PaperRecord(**data)


def test_literature_review_generation_supports_exports_and_critique() -> None:
    service = LiteratureReviewService()
    response = service.generate(
        LiteratureReviewRequest(
            title="Resora Literature Review",
            extracted_text="This review studies multimodal retrieval systems, benchmark datasets, and trust-aware synthesis. It highlights limitations and future directions.",
            figures=[
                ExtractedFigure(
                    figure_id="fig-1",
                    caption="Figure 1: Retrieval accuracy across benchmark datasets",
                    chart_type="line",
                    description="Accuracy trend",
                    data_insights=["Accuracy rises after hybrid fusion"],
                )
            ],
            tables=[
                ExtractedTable(
                    table_id="tab-1",
                    caption="Table 1: Benchmark comparison",
                    headers=["Method", "Accuracy"],
                    rows=[["Hybrid", "89"]],
                    csv_export="Method,Accuracy\nHybrid,89",
                )
            ],
            target_style="ieee",
            citation_style="apa",
            tone="formal",
            word_count_target=1200,
            section_length_targets={"Abstract": 25},
            target_journal="IEEE Access",
            disclosure_watermark=True,
            regenerate_instruction="Make conclusion more evidence-led.",
            comments=["Please strengthen the conclusion."],
        )
    )
    assert response.outline
    assert "Abstract" in response.outline
    assert response.sections["Introduction"].startswith("In IEEE tone")
    assert response.target_style_adaptation["target"] == "IEEE Access"
    assert response.paragraph_citation_map
    assert "vancouver" in response.citation_style_previews
    assert response.reference_list
    assert response.self_critique["supported_claims"] is not None
    assert response.plagiarism_report["plagiarism_risk"] in {"low", "review-needed"}
    assert response.section_details
    assert response.section_details[0].source_span
    assert response.critique_trace
    assert response.critique_trace[0].verdict in {"supported", "unsupported"}
    assert response.export_formats["latex"].startswith("\\section*")
    assert "\\documentclass" in response.overleaf_export
    assert "bibtex" in response.export_formats
    assert response.word_count_report["target"] == 1200
    assert response.section_regeneration["status"] == "not-requested"
    assert response.academic_style_corrections
    assert response.figure_table_insertions
    assert response.export_artifacts[0].file_name.endswith((".md", ".tex", ".docx", ".pdf"))
    artifacts_by_format = {artifact.format: artifact for artifact in response.export_artifacts}
    assert artifacts_by_format["pdf"].storage_uri
    assert Path(artifacts_by_format["pdf"].storage_uri).read_bytes().startswith(b"%PDF")
    assert artifacts_by_format["docx"].storage_uri
    assert zipfile.is_zipfile(artifacts_by_format["docx"].storage_uri)
    assert artifacts_by_format["docx"].byte_size > 0
    assert response.cover_letter.startswith("Dear Editor")
    assert response.peer_review_response.startswith("We thank the reviewers")
    assert response.watermark is not None
    assert response.confidence_score > 0
    assert response.generated_at


def test_literature_review_section_regeneration_and_rollback_metadata() -> None:
    service = LiteratureReviewService()
    response = service.generate(
        LiteratureReviewRequest(
            title="Section Rewrite",
            extracted_text="Smith et al. 2025 report benchmark improvements and limitations.",
            section_only="Conclusion",
            regenerate_instruction="Make it stronger.",
            rollback_to_version="v1",
        )
    )
    assert response.outline == ["Conclusion"]
    assert response.section_regeneration["status"] == "ready"
    assert response.rollback_preview
    assert response.rollback_preview["version"] == "v1"


def test_citation_library_handles_duplicates_and_style_preview() -> None:
    service = CitationLibraryService()
    papers = [
        make_paper(),
        make_paper(
            paper_id="w2",
            title="Hybrid Retrieval Benchmark Dataset",
            doi="10.1000/resora.2",
            authors=[{"name": "John Smith"}],
        ),
    ]
    saved = service.save(
        CitationLibraryRequest(
            papers=papers,
            folder="Core",
            collection="Deepfake/RAG",
            tags=["rag", "benchmark"],
            workspace_id="ws-1",
            shared_team_library=True,
            persistent_highlights={"w1": ["Hybrid retrieval improves accuracy."]},
        )
    )
    preview = service.preview(CitationPreviewRequest(paper=papers[0], style="ieee"))
    assert saved.saved_items
    assert saved.duplicate_groups
    assert "@article" in saved.bibliography_export
    assert saved.library_stats["workspace_scope"] == "ws-1"
    assert saved.unread_queue == [item.paper_id for item in saved.saved_items]
    assert saved.export_artifacts["primary"].endswith(".bib")
    assert saved.folder_tree["Deepfake/RAG"] == ["w1", "w2"]
    assert saved.tag_index["rag"] == ["w1", "w2"]
    assert saved.citation_impact_tracking["w1"]
    assert saved.personal_citation_graph["nodes"]
    assert "csljson" in saved.full_library_bibliography_exports
    assert saved.annotated_pdf_library["w1"] == ["Hybrid retrieval improves accuracy."]
    assert saved.persistence_uri
    assert Path(saved.persistence_uri).exists()
    assert saved.saved_items[0].open_access_resolution
    assert saved.saved_items[0].doi_lookup == "10.1000/resora.1"
    assert preview.preview.startswith("[1]")
    assert preview.style == "ieee"
    assert "vancouver" in preview.format_options
    assert preview.live_style_previews["apa"]
    assert preview.dead_doi_check == "healthy"
    assert preview.doi_lookup == "10.1000/resora.1"


def test_citation_library_imports_bibtex_payloads() -> None:
    service = CitationLibraryService()
    payload = """@article{hybrid2025,
  title = {Hybrid Retrieval Benchmark Dataset},
  author = {Ali Khan and Sara Noor},
  journal = {Journal of AI Systems},
  year = {2025},
  doi = {10.1000/resora.1},
  url = {https://example.org/w1}
}"""
    imported = service.import_records(CitationImportRequest(format="bibtex", payload=payload, folder="Imported", tags=["seed"]))
    assert imported.imported_items
    assert imported.imported_items[0].import_source == "bibtex-import"
    assert imported.imported_items[0].folder == "Imported"
    assert imported.import_summary.startswith("Imported 1 records")
    assert imported.roundtrip_exports["bibtex"]


def test_collaboration_workspace_summary_exposes_team_controls() -> None:
    service = CollaborationService()
    response = service.summarize(
        CollaborationRequest(
            workspace_id="ws-1",
            comments=[CommentThread(resource_type="draft", resource_id="d1", comments=["Needs more evidence"], participants=["Supervisor", "Haroon"])],
            tasks=[WorkspaceTask(title="Revise conclusion", assignee="Areesha", status="open", priority="high", due_in_days=1, linked_resource_type="draft", linked_resource_id="d1")],
            mentions=["Haroon", "Supervisor"],
            review_mode="comment-only",
            shared_folders=["Core Papers", "Supervisor Notes"],
            meeting_notes=["meeting-12"],
            live_document_text="Initial literature review draft.",
            concurrent_edits=[
                {"operation": "append", "text": "Haroon added evidence notes."},
                {"operation": "replace", "target": "Initial", "text": "Updated"},
            ],
            ai_generated_events=[{"actor": "resora", "action": "draft-summary-generated", "resource_id": "d1"}],
            ai_quota_overrides={"editor": 750},
            guest_review_enabled=True,
            share_expiry_days=14,
            collaborator_roles={"Haroon": "editor", "Supervisor": "supervisor", "Areesha": "editor"},
            template_name="thesis-supervision",
        )
    )
    assert response.activity_feed
    assert response.notifications
    assert response.team_dashboard["open_tasks"] == 1
    assert response.team_dashboard["guest_review_links"] == 1
    assert response.guest_link == "guest-ws-1"
    assert response.ai_usage_quotas["owner"] == 1000
    assert response.ai_usage_quotas["editor"] == 750
    assert response.share_links
    assert response.share_links[0].permission == "comment"
    assert response.share_links[0].expires_in_days == 14
    assert response.task_board["open"] == 1
    assert response.member_presence
    assert response.task_assignments
    assert response.task_assignments[0].overdue_risk >= 0
    assert response.review_checkpoints[0].label == "Evidence pass"
    assert response.collaborator_roles["Supervisor"] == "supervisor"
    assert "Core Papers" in response.shared_folder_summary
    assert response.guest_review_policy["enabled"] is True
    assert response.review_threads_by_resource["draft:d1"] == 1
    assert response.mention_directory["Haroon"] == "editor"
    assert response.checkpoint_export_status["audit_log"] == "attached"
    assert response.realtime_channels
    assert response.inline_comment_threads[0].participants == ["Supervisor", "Haroon"]
    assert response.digest_delivery_receipts
    assert response.ai_content_audit_log[0].action == "draft-summary-generated"
    assert response.concurrent_edit_state
    assert response.concurrent_edit_state.operations_applied == 2
    assert "Haroon added evidence notes" in response.concurrent_edit_state.merged_text
    assert response.research_packet_archive_uri
    assert zipfile.is_zipfile(response.research_packet_archive_uri)
    assert response.research_packet_byte_size > 0
    assert response.workspace_snapshot_uri
    assert Path(response.workspace_snapshot_uri).exists()
    assert "thesis-supervision" in response.template_workspace
    assert "supervisor" in response.rbac_matrix
    assert "grant-writing" in response.template_workspace_options
    assert response.generated_at


def test_personalization_supports_accessibility_and_offline_modes() -> None:
    service = PersonalizationService()
    response = service.build(
        PersonalizationRequest(
            user_type="student",
            reading_history=["multimodal retrieval benchmark", "urdu accessibility interface"],
            verbosity="beginner",
            offline_items=["paper-1", "paper-2"],
            low_bandwidth=True,
            ui_language="ur",
            rtl_enabled=True,
            theme="contrast",
            font_size="xl",
            dyslexia_friendly=True,
            tts_enabled=True,
            dashboard_widgets=["Reading Queue", "Glossary", "Offline Shelf"],
            digest_frequency="daily",
            device_ids=["laptop", "phone"],
            glossary_seed_terms=["RAG", "OCR"],
            data_action="export",
        )
    )
    assert response.recommended_topics
    assert "Low-bandwidth summary cards" in response.dashboard_widgets
    assert response.accessibility_profile["font_size"] == "xl"
    assert response.accessibility_profile["direction"] == "rtl"
    assert response.urdu_ui["enabled"] is True
    assert response.font_controls["dyslexia_friendly"] is True
    assert response.tts_controls["scope"] == "any content"
    assert response.wcag_aa_checklist["keyboard_access"] is True
    assert response.screen_reader_landmarks
    assert response.keyboard_navigation_map
    assert response.contextual_help_tooltips["offline"]
    assert response.color_blind_safe_palette["background"] == "#000000"
    assert response.offline_reading_list[0]["key"] == "paper-1"
    assert "paper-1" in response.pwa_cache_manifest["reading_cache"]
    assert response.low_bandwidth_mode["enabled"] is True
    assert response.multi_device_sync["device_count"] == 2
    assert response.customizable_dashboard["selected_widgets"]
    assert response.similar_to_read_feed
    assert response.ai_preferences["verbosity"] == "beginner"
    assert response.personal_glossary["RAG"]
    assert response.scheduled_digest["frequency"] == "daily"
    assert response.data_export_uri
    assert Path(response.data_export_uri).exists()
    assert response.profile_snapshot_uri
    assert Path(response.profile_snapshot_uri).exists()
    assert "offline items ready to sync" in response.sync_status


def test_analytics_builds_network_and_workspace_views() -> None:
    service = AnalyticsService()
    response = service.build(
        AnalyticsRequest(
            papers=[
                make_paper(),
                make_paper(
                    paper_id="w3",
                    title="Graph Methods for Clinical Benchmarking",
                    abstract="This benchmark dataset studies graph retrieval and corpus construction.",
                    year=2024,
                    authors=[{"name": "John Smith"}, {"name": "Ali Khan"}],
                    citation_count=63,
                ),
            ],
            workspace_id="ws-1",
            citation_edges=[
                {"source": "w1", "target": "w3", "sentiment": "support"},
                {"source": "w3", "target": "w1", "sentiment": "dispute"},
            ],
            activity_events=[
                {"type": "search", "count": 1},
                {"type": "draft", "count": 1},
            ],
            auto_refresh_seconds=15,
        )
    )
    assert response.citation_network_graph["nodes"]
    assert response.pagerank_scores
    assert response.influence_scores
    assert response.citation_velocity
    assert response.time_slider_frames
    assert response.network_growth
    assert response.trend_chart["2024"] == 1
    assert response.research_trend_series
    assert response.methodology_heatmap
    assert response.methodology_heatmap_labels["rows"]
    assert response.comparison_heatmap_drilldown
    assert response.coauthorship_graph["nodes"]
    assert response.geographic_distribution_points
    assert response.research_journey_timeline
    assert response.dataset_usage_chart
    assert response.benchmark_leaderboard_chart
    assert response.gap_topic_map
    assert response.chart_snippets
    assert response.exportable_chart_snippets["trend_svg"].startswith("<svg")
    assert response.citation_sentiment_distribution["support"] == 1
    assert response.citation_sentiment_chart
    assert response.reading_difficulty_chart
    assert response.workspace_activity_chart
    assert response.live_dashboard_config["refresh_seconds"] == 15
    assert response.auto_refresh_note
