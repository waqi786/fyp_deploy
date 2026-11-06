from app.schemas.paper import PaperRecord
from app.services.search.discovery import (
    _extract_datasets,
    _extract_methodologies,
    apply_filters,
    build_discovery_facets,
    enrich_search_results,
    infer_metadata_fields,
    interpret_search_query,
    normalize_natural_language_query,
    semantic_vector_scores,
)
from app.services.summarization.extractive import ExtractiveSummarizer


def test_search_facets_do_not_create_placeholder_methods_or_datasets() -> None:
    assert _extract_datasets("The authors discuss dataset availability.") == []
    assert _extract_methodologies("A study about the electronic markets.") == []


def make_paper(**overrides) -> PaperRecord:
    data = {
        "paper_id": "p1",
        "title": "Hybrid Retrieval Benchmark Dataset",
        "abstract": "We introduce a benchmark dataset with n = 120 samples. Our method improves F1 and reports p < 0.05. Figure 1: Benchmark comparison. Future work includes multilingual evaluation.",
        "year": 2024,
        "venue": "AI Journal",
        "citation_count": 140,
        "reference_count": 25,
        "is_open_access": True,
        "authors": [{"name": "Alice"}],
        "source": "openalex",
    }
    data.update(overrides)
    return PaperRecord(**data)


def test_query_normalization_handles_multilingual_path() -> None:
    normalized, translated = normalize_natural_language_query("machine learning zaban", "ur")
    assert normalized
    assert translated is not None


def test_query_normalization_translates_common_research_terms_across_scripts() -> None:
    cases = [
        ("\u0627\u0644\u0630\u0643\u0627\u0621 \u0627\u0644\u0627\u0635\u0637\u0646\u0627\u0639\u064a", "en", "artificial intelligence"),
        ("\u4eba\u5de5\u667a\u80fd", "en", "artificial intelligence"),
        ("\u0915\u0943\u0924\u094d\u0930\u093f\u092e \u092c\u0941\u0926\u094d\u0927\u093f\u092e\u0924\u094d\u0924\u093e", "hi", "artificial intelligence"),
        ("\u0645\u0635\u0646\u0648\u0639\u06cc \u0630\u06c1\u0627\u0646\u062a", "ur", "artificial intelligence"),
        ("\u0645\u0635\u0646\u0641 Geoffrey Hinton \u0627\u0639\u0635\u0627\u0628\u06cc \u0646\u06cc\u0679 \u0648\u0631\u06a9", "ur", "author Geoffrey Hinton neural networks"),
    ]

    for query, language, expected in cases:
        normalized, translated = normalize_natural_language_query(query, language)
        assert expected in normalized
        assert translated is not None


def test_search_enrichment_adds_ranking_clusters_and_badges() -> None:
    paper = infer_metadata_fields(make_paper())
    ranked, clusters, suggestions, trending = enrich_search_results("hybrid retrieval", [paper], search_mode="hybrid", sort_by="relevance")
    assert ranked[0].ranking_score > 0
    assert ranked[0].cluster_label
    assert ranked[0].result_badges
    assert ranked[0].micro_summary
    assert clusters
    assert suggestions
    assert trending


def test_rag_intent_ranks_retrieval_papers_above_generic_hybrid_dataset() -> None:
    papers = [
        infer_metadata_fields(
            make_paper(
                paper_id="generic-hybrid",
                title="A comprehensive benchmark dataset for SSVEP-based hybrid BCI",
                abstract="This paper introduces a benchmark dataset for hybrid brain-computer interfaces.",
                citation_count=200,
            )
        ),
        infer_metadata_fields(
            make_paper(
                paper_id="rag-match",
                title="CRAG - Comprehensive RAG Benchmark",
                abstract="A retrieval-augmented generation benchmark dataset for evaluating RAG systems.",
                citation_count=12,
            )
        ),
    ]

    ranked, _, _, _ = enrich_search_results("hybrid rag benchmark dataset", papers, search_mode="hybrid", sort_by="relevance")

    assert ranked[0].paper_id == "rag-match"


def test_semantic_vector_scores_rank_abstract_meaning_not_only_title_terms() -> None:
    papers = [
        infer_metadata_fields(
            make_paper(
                paper_id="semantic-match",
                title="Evidence Mapping for Research Assistants",
                abstract="Dense semantic retrieval ranks papers by vector similarity, meaning overlap, and academic concept alignment.",
                citation_count=20,
            )
        ),
        infer_metadata_fields(
            make_paper(
                paper_id="title-only",
                title="Protein Folding Survey",
                abstract="This review studies molecule structure prediction.",
                citation_count=200,
            )
        ),
    ]

    scores = semantic_vector_scores("semantic vector similarity", papers)
    ranked, _, _, _ = enrich_search_results("semantic vector similarity", papers, search_mode="semantic", sort_by="relevance")

    assert scores["semantic-match"] > scores.get("title-only", 0)
    assert ranked[0].paper_id == "semantic-match"


def test_search_filters_respect_open_access_and_citations() -> None:
    papers = [
        infer_metadata_fields(make_paper(citation_count=5, is_open_access=False)),
        infer_metadata_fields(make_paper(paper_id="p2", citation_count=200, is_open_access=True)),
    ]
    filtered = apply_filters(
        papers,
        min_citations=100,
        open_access_only=True,
        study_type=None,
        quartile=None,
        sample_size_min=100,
        year_from=2020,
        year_to=2026,
        methodology=None,
        author=None,
        venue=None,
        institution=None,
        dataset=None,
        peer_reviewed_only=False,
        preprint_only=False,
        include_retracted=True,
    )
    assert len(filtered) == 1
    assert filtered[0].paper_id == "p2"


def test_query_interpretation_handles_voice_and_spell_correction() -> None:
    interpretation = interpret_search_query(
        "retrival acadmic search",
        language="en",
        query_type="voice",
        voice_transcript="retrival acadmic search",
    )
    assert interpretation["normalized_query"] == "retrieval academic search"
    assert interpretation["boolean_query"]


def test_discovery_facets_surface_networks_and_recommendations() -> None:
    papers = [
        infer_metadata_fields(
            make_paper(
                authors=[{"name": "Alice", "institution": "PUCIT"}, {"name": "Bilal", "institution": "PUCIT"}],
                abstract="We release the Resora Dataset and provide code at https://github.com/resora/search.",
            )
        )
    ]
    facets = build_discovery_facets(papers, query="figure benchmark", query_type="image", image_caption="benchmark comparison figure")
    assert facets["author_network"]
    assert facets["author_disambiguation"]
    assert facets["venue_matches"] == ["AI Journal"]
    assert facets["institution_matches"] == ["PUCIT"]
    assert facets["dataset_matches"]
    assert facets["code_repository_matches"]
    assert facets["recommended_papers"]
    assert facets["figure_search_matches"]
    assert "openalex" in facets["source_coverage"]
    assert facets["search_insights"]["semantic_rerank_enabled"] is True


def test_discovery_facets_include_relationship_pairs() -> None:
    papers = [
        infer_metadata_fields(
            make_paper(
                paper_id="p1",
                title="Hybrid Retrieval Benchmark Dataset",
                abstract="We evaluate a Benchmark Dataset with Transformer retrieval. Figure 1: Retrieval comparison.",
                authors=[{"name": "Alice", "institution": "PUCIT"}],
            )
        ),
        infer_metadata_fields(
            make_paper(
                paper_id="p2",
                title="Hybrid Retrieval Benchmark Analysis",
                abstract="This study uses the Benchmark Dataset with Transformer baselines and reports strong citations.",
                authors=[{"name": "Alice", "institution": "FAST"}],
                citation_count=150,
            )
        ),
    ]
    facets = build_discovery_facets(papers, query="hybrid retrieval benchmark")
    assert facets["co_citation_pairs"]
    assert facets["bibliographic_coupling_pairs"]


def test_summary_enrichment_returns_academic_features() -> None:
    summarizer = ExtractiveSummarizer()
    response = summarizer.summarize(
        "Hybrid Retrieval Benchmark Dataset",
        "We introduce a benchmark dataset with n = 120 samples. Our method uses RAG and BM25. Results improve F1 and report p < 0.05. Figure 1: Benchmark comparison. Future work includes multilingual evaluation.",
        language="en",
        audience="beginner",
        summary_length="long",
    )
    assert response.glossary is not None
    assert response.difficulty_score in {"Easy", "Medium", "Expert"}
    assert response.contributions
    assert response.limitations
    assert response.datasets
    assert response.reproducibility_checklist
    assert response.reading_time_minutes >= 1
    assert response.acronym_expansions
    assert response.exam_qa
    assert response.summary_tiers["5_min"].source_spans
    assert response.glossary_entries
    assert response.hover_glossary_spans
    assert response.translation_languages
    assert response.audience_mode == "beginner"
    assert response.audience_guidance
    assert response.summary_length_applied == "long"
    assert response.paragraph_explainability_preview
    assert response.outline_sections
    assert response.fallback_used is False


def test_search_service_emits_ranking_and_prefetch_metadata() -> None:
    from app.services.search.service import FederatedSearchService

    class StubProvider:
        source_name = "openalex"

        async def search(self, request):  # noqa: ANN001
            return [
                infer_metadata_fields(
                    make_paper(
                        paper_id="stub-1",
                        title="Hybrid Retrieval Benchmark Dataset",
                        abstract="This benchmark dataset supports semantic retrieval and figure analysis.",
                        venue="AI Journal",
                    )
                ),
                infer_metadata_fields(
                    make_paper(
                        paper_id="stub-2",
                        title="Hybrid Retrieval Benchmark Analysis",
                        abstract="This work compares BM25 and semantic reranking for academic search.",
                        venue="ML Proceedings",
                    )
                ),
            ]

    class StubWebSearch:
        async def search(self, query, limit=10):
            return []

    service = FederatedSearchService(providers={"openalex": StubProvider()}, web_search=StubWebSearch())
    response = __import__("asyncio").run(
        service.search("hybrid retrieval benchmark", 1, ["openalex"], page=1, save_history=False)
    )
    assert response.ranking_explanations
    assert response.ranking_explanations[0].reasons
    assert response.venue_matches
    assert response.lazy_prefetch_window
    assert response.search_insights["advanced_query_blocks"]
    assert response.search_insights["semantic_backend"] == "faiss_lite"
    assert response.search_insights["semantic_vector_indexed_results"] == 2


def test_paragraph_explain_response_includes_reader_metadata() -> None:
    summarizer = ExtractiveSummarizer()
    explanation = summarizer.explain(
        "This paragraph explains a benchmark result with p < 0.05 and a strong baseline gain.",
        audience="expert",
        language="en",
    )
    assert explanation["audience_mode"] == "expert"
    assert explanation["reading_level"] == "advanced"
    assert explanation["source_span"].startswith("paragraph:1:")
