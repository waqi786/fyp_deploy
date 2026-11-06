from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

from app.cli import main as cli_main
from app.schemas.advanced import AdvancedAIRequest
from app.schemas.developer import BrowserExtensionIntakeRequest, DeveloperPlatformRequest, GraphQLQueryRequest
from app.schemas.paper import PaperRecord
from app.services.advanced.intelligence import AdvancedIntelligenceService
from app.services.developer.platform import DeveloperPlatformService
from app.services.plugins.registry import PluginRegistryService


def make_paper(**overrides) -> PaperRecord:
    data = {
        "paper_id": "a1",
        "title": "Cross Lingual Retrieval Benchmark",
        "abstract": "This paper improves retrieval quality and reports F1 88.2 with multilingual evidence. However, limitations remain in noisy settings.",
        "year": 2025,
        "venue": "AI Review",
        "citation_count": 44,
        "is_open_access": True,
        "authors": [{"name": "Ali Khan"}],
        "source": "openalex",
        "language": "ur",
    }
    data.update(overrides)
    return PaperRecord(**data)


def test_developer_platform_supports_keys_graphql_imports_and_extension() -> None:
    service = DeveloperPlatformService()
    response = service.build(
        DeveloperPlatformRequest(
            user_id="u1",
            workspace_id="w1",
            reference_blob='[{"paper_id":"i1","title":"Imported Study","year":2024,"source":"json"}]',
            reference_format="json",
            prompt_templates={"debate": "Present strongest pro and con evidence."},
            webhook_events=["search.match.created", "workspace.mention.created"],
            plugin_filters=["data_source", "llm_provider"],
        )
    )
    graphql = service.graphql(GraphQLQueryRequest(query="query { health plugins usage apiKeys }"))
    intake = service.extension_intake(BrowserExtensionIntakeRequest(title="Paper", url="https://example.org", selection="Important abstract text"))
    assert response.issued_api_key.startswith("rsr_live_")
    assert response.api_key_summary.key_prefix.startswith("rsr_live_")
    assert response.api_key_summary.revocation_endpoint == "/api/v1/developer/api-keys/revoke"
    assert response.api_key_lifecycle
    assert response.openapi_url == "/docs"
    assert response.graphql_endpoint == "/api/v1/developer/graphql"
    assert response.imported_references[0].title == "Imported Study"
    assert response.plugin_summary["data_source"]
    assert response.plugin_capabilities
    assert response.webhook_preview.retry_policy == "exponential-backoff"
    assert response.webhook_preview.signature_header.startswith("X-Resora-Signature:")
    assert response.webhook_preview.delivery_receipt_id.startswith("wh_")
    assert response.integration_sync_jobs
    assert response.extension_manifest["name"] == "Send to Resora"
    assert response.saved_prompt_template_ids
    assert response.import_job.imported_count == 1
    assert Path(str(response.import_job.artifact_uri)).exists()
    assert response.bulk_import_artifact_uri == response.import_job.artifact_uri
    assert response.admin_dashboard.plugin_count >= 2
    assert response.admin_dashboard.usage_by_route["/api/v1/search"] > 0
    assert response.admin_health_checks
    assert response.developer_audit_events
    assert response.generated_at
    assert "health" in graphql.data
    assert "plugins" in graphql.data
    assert intake.status == "queued"
    assert intake.saved_item_id.startswith("ext-")
    assert intake.route_hint == "library-inbox"


def test_plugin_registry_lists_sources_and_llms() -> None:
    registry = PluginRegistryService()
    summary = registry.summary()
    assert "openalex" in summary["data_source"]
    assert "groq" in summary["llm_provider"]


def test_advanced_intelligence_supports_debate_guardrails_and_review_updates(monkeypatch) -> None:
    # Keep this workflow test offline and deterministic; translation-provider
    # behavior is covered separately with fake adapters.
    from app.services.search import translation

    monkeypatch.setattr(translation, "translate_batch", lambda segments, *_args, **_kwargs: list(segments))
    monkeypatch.setattr(translation, "translate_text", lambda text, *_args, **_kwargs: text)
    service = AdvancedIntelligenceService()
    response = service.analyze(
        AdvancedAIRequest(
            question="Debate whether cross-lingual retrieval improves benchmark performance and explain the ranking.",
            papers=[
                make_paper(),
                make_paper(
                    paper_id="a2",
                    title="Benchmark Skepticism for Retrieval",
                    abstract="This review underperforms on AUC 71.5 and highlights bias, limitation, and fairness concerns.",
                    language="en",
                    citation_count=31,
                ),
            ],
            language="en",
            mode="debate",
            current_review_paper_ids=["a2"],
            subscription_query="cross-lingual retrieval",
        )
    )
    assert response.plan
    assert response.agent_state_machine
    assert response.specialist_outputs["statistician"]
    assert response.orchestration_confidence["statistician"] > 0
    assert response.retrieval_depth >= 5
    assert response.adaptive_retrieval_policy["selected_depth"] == response.retrieval_depth
    assert response.grounded_citations
    assert response.workflow_trace
    assert response.evidence_trace
    assert response.evidence_trace[0].support_type in {"supporting", "contesting", "context"}
    assert response.debate_mode["for"]
    assert response.debate_mode["against"]
    assert response.review_update["new_papers"] == ["a1"]
    assert response.review_diff_detail["added"] == ["a1"]
    assert response.guardrail_decisions
    assert response.guardrail_decisions[0].rule == "retrievable-evidence-required"
    assert response.zero_hallucination_report["status"] == "enforced"
    assert response.self_critique_summary["unsupported_claims_omitted"] == len(response.omitted_claims)
    assert response.benchmark_summary
    assert response.benchmark_reasoning_table
    assert response.explainable_ranking
    assert response.ranking_explanations
    assert response.critique_panel["ethics"]
    assert response.perspective_panel["statistician"]
    assert response.auto_review_subscription["enabled"] is True
    assert response.cross_lingual_retrieval_map
    assert response.translated_evidence
    assert response.generated_at


def test_cli_admin_summary_and_import_refs(tmp_path: Path) -> None:
    refs_path = tmp_path / "refs.json"
    refs_path.write_text('[{"paper_id":"c1","title":"CLI Import","year":2024,"source":"json"}]', encoding="utf-8")

    capture = StringIO()
    with redirect_stdout(capture):
        exit_code = cli_main(["admin-summary"])
    assert exit_code == 0
    assert "system_health" in capture.getvalue()

    capture = StringIO()
    with redirect_stdout(capture):
        exit_code = cli_main(["import-refs", "--format", "json", "--input", str(refs_path)])
    assert exit_code == 0
    assert "CLI Import" in capture.getvalue()
