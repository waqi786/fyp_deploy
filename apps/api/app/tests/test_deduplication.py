from app.schemas.paper import PaperRecord
from app.services.search.deduplication import deduplicate_papers, normalize_title, score_paper_richness


def make_paper(**overrides) -> PaperRecord:
    data = {
        "paper_id": "p1",
        "title": "A Study on Hybrid Retrieval",
        "abstract": "This paper proposes a strong hybrid retrieval pipeline for grounded academic chat systems.",
        "year": 2024,
        "venue": "Journal of AI",
        "doi": "10.1000/example-doi",
        "url": "https://doi.org/10.1000/example-doi",
        "pdf_url": "https://example.com/paper.pdf",
        "citation_count": 10,
        "reference_count": 20,
        "is_open_access": True,
        "authors": [{"name": "Alice"}],
        "source": "openalex",
        "external_ids": {"DOI": "10.1000/example-doi"},
    }
    data.update(overrides)
    return PaperRecord(**data)


def test_normalize_title_collapses_whitespace_and_punctuation() -> None:
    assert normalize_title("A Study: on Hybrid   Retrieval!") == "a study on hybrid retrieval"


def test_score_paper_richness_matches_baseline_rules() -> None:
    assert score_paper_richness(make_paper()) == 9
    assert score_paper_richness(make_paper(abstract="too short", citation_count=0, pdf_url=None, is_open_access=False, year=None)) == 0


def test_deduplicate_papers_prefers_richer_record_and_merges_sources() -> None:
    first = make_paper(source="openalex", citation_count=2, abstract=None, pdf_url=None)
    second = make_paper(
        paper_id="p2",
        source="crossref",
        citation_count=15,
        abstract="This is a much richer abstract that easily exceeds the fifty character threshold for scoring.",
        pdf_url="https://example.com/rich.pdf",
    )

    result = deduplicate_papers([first, second])

    assert result.duplicates_removed == 1
    assert len(result.papers) == 1
    assert result.papers[0].citation_count == 15
    assert result.papers[0].pdf_url == "https://example.com/rich.pdf"
    assert result.papers[0].all_sources == ["crossref", "openalex"]
    assert result.likely_duplicate_pairs == []


def test_deduplicate_papers_merges_semantic_near_duplicates_without_exact_title_or_doi() -> None:
    first = make_paper(
        paper_id="semantic-1",
        title="Hybrid Retrieval for Literature Review Assistants",
        doi=None,
        url="https://example.com/a",
        external_ids={},
        authors=[{"name": "Alice Noor"}],
    )
    second = make_paper(
        paper_id="semantic-2",
        title="Hybrid Retrieval for AI Literature Review Assistant",
        doi=None,
        url="https://example.com/b",
        external_ids={},
        source="semantic_scholar",
        authors=[{"name": "Alice Noor"}],
        abstract="This paper proposes a strong hybrid retrieval pipeline for grounded academic chat systems in literature review assistants.",
    )

    result = deduplicate_papers([first, second])

    assert result.duplicates_removed == 1
    assert len(result.papers) == 1
    assert sorted(result.papers[0].all_sources) == ["openalex", "semantic_scholar"]
