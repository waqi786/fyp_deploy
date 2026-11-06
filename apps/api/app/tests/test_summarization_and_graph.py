from app.schemas.graph import CitationEdge, CitationGraphRequest, CitationNode
from app.services.models.providers import ModelProvider
from app.services.graph.metrics import CitationGraphService
from app.services.summarization.extractive import ExtractiveSummarizer
from app.services.writing.self_critique import SelfCritiqueService


def test_extractive_summarizer_returns_structured_sections() -> None:
    summarizer = ExtractiveSummarizer()
    response = summarizer.summarize(
        "Paper",
        "This paper studies retrieval. It uses hybrid ranking. Results show stronger accuracy than single-mode baselines. The conclusion recommends grounded academic chat. E = mc^2.",
    )
    assert response.structured_summary["problem"]
    assert response.bullet_summary
    assert response.equations
    assert response.urdu_summary["problem"]
    assert response.summary_tiers["30_sec"].content
    assert response.source_spans
    assert response.generated_at
    assert response.related_work_summary
    assert response.audio_narration["plain_text"]
    assert response.translations["ur"]["tldr"]
    assert isinstance(response.study_limitation_severity_score, float)


def test_extractive_summarizer_falls_back_to_valid_schema_when_provider_fails() -> None:
    class FailingProvider(ModelProvider):
        provider_name = "failing-provider"

        def __init__(self) -> None:
            pass

        def structured_sections(self, title: str, content: str) -> dict[str, str]:
            raise RuntimeError("provider down")

    summarizer = ExtractiveSummarizer(provider=FailingProvider())
    response = summarizer.summarize(
        "Fallback Paper",
        "We introduce a benchmark dataset. Our methodology uses hybrid retrieval. Results improve accuracy. Future work includes multilingual evaluation.",
    )

    assert response.structured_summary["problem"]
    assert response.summary_tiers["2_min"].content
    assert response.fallback_used is True
    assert response.model_used == "failing-provider"


def test_reader_summary_localizes_selected_language_without_fake_prefixes(monkeypatch) -> None:
    # Use a deterministic fake translation engine; test data must never call a live model.
    from app.services.search import translation

    def fake_translate(text, target_language, **_kwargs):
        if target_language == "ur":
            return "ذیابیطس میں مشین لرننگ اور ماضی میں نتائج"
        return "La predicción utiliza regresión logística y modelos de aprendizaje."

    monkeypatch.setattr(translation, "translate_text", fake_translate)
    summarizer = ExtractiveSummarizer()
    content = (
        "This paper compares logistic regression and machine learning models for diabetes prediction. "
        "The method uses a dataset with 120 samples. Results show better accuracy than baseline models. "
        "Future work discusses limitations and external validation."
    )

    urdu = summarizer.summarize("Diabetes Prediction", content, language="ur", audience="beginner", summary_length="medium")
    spanish = summarizer.summarize("Diabetes Prediction", content, language="es", audience="expert", summary_length="medium")

    assert "ذیابیطس" in urdu.tldr
    assert "مشین لرننگ" in " ".join(urdu.bullet_summary)
    assert not urdu.tldr.startswith("UR")
    assert "diabetes" in spanish.tldr.lower() or "predicción" in spanish.tldr.lower()
    assert not spanish.tldr.startswith("Resumen:")
    assert "regresión logística" in spanish.deep_dive


def test_reader_summary_depth_changes_generated_detail() -> None:
    summarizer = ExtractiveSummarizer()
    content = (
        "This paper studies retrieval. It uses hybrid ranking. Results show stronger accuracy than single-mode baselines. "
        "The dataset includes 120 samples. Figure 1 shows benchmark comparison. Future work includes multilingual evaluation. "
        "The limitation is external validation. Code availability supports reproducibility."
    )

    short = summarizer.summarize("Retrieval Study", content, language="en", audience="expert", summary_length="short")
    long = summarizer.summarize("Retrieval Study", content, language="en", audience="expert", summary_length="long")

    assert len(short.bullet_summary) < len(long.bullet_summary)
    assert len(short.deep_dive) < len(long.deep_dive)


def test_paragraph_explain_returns_reader_aids() -> None:
    summarizer = ExtractiveSummarizer()
    result = summarizer.explain(
        "Our method combines BM25 and RAG to improve grounded retrieval across multilingual questions.",
        audience="beginner",
        language="en",
    )
    assert result["explanation"]
    assert result["simplified_points"]
    assert isinstance(result["glossary_terms"], dict)
    assert result["confidence_score"] > 0


def test_citation_graph_service_returns_bridge_nodes() -> None:
    service = CitationGraphService()
    result = service.analyze(
        CitationGraphRequest(
            roots=["r1", "r2"],
            nodes=[
                CitationNode(paper_id="r1", title="Root 1", year=2022, citation_count=20),
                CitationNode(paper_id="r2", title="Root 2", year=2021, citation_count=10),
                CitationNode(paper_id="b1", title="Bridge", year=2023, citation_count=5),
            ],
            edges=[
                CitationEdge(source="b1", target="r1"),
                CitationEdge(source="b1", target="r2"),
            ],
        )
    )
    assert "b1" in result.bridge_nodes
    assert result.influence_scores["r1"] >= 0


def test_self_critique_flags_unsupported_claims() -> None:
    critique = SelfCritiqueService().critique(
        "Hybrid retrieval improves accuracy. This paper also cures every disease.",
        ["paper-1: Hybrid retrieval improves accuracy and grounding in our benchmark."],
    )
    assert critique["supported_claims"]
    assert critique["unsupported_claims"]
