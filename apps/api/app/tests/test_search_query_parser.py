import pytest

from app.schemas.paper import PaperRecord
from app.services.search.query_parser import understand_research_query
from app.services.search.service import FederatedSearchService


@pytest.mark.parametrize(
    ("query", "expected", "year", "open_access", "author", "reviews"),
    [
        ("Hey I wanna search machine learning papers kindly search it.", "machine learning", None, False, None, False),
        ("Please search papers about graph neural networks from 2020.", "graph neural networks", 2020, False, None, False),
        ("Find me papers about climate change open access.", "climate change", None, True, None, False),
        ("Search for deep learning papers by Yoshua Bengio.", "deep learning", None, False, "Yoshua Bengio", False),
        ("Can you search systematic reviews about cancer?", "cancer", None, False, None, True),
        ("Kindly search it about machine learning.", "machine learning", None, False, None, False),
        ("I would like to search papers about federated learning since 2021.", "federated learning", 2021, False, None, False),
        ("search for me papers about RAG from 2022 open access", "RAG", 2022, True, None, False),
        ("mujhe machine learning papers chahiye", "machine learning", None, False, None, False),
        ("براہ کرم مشین لرننگ کے بارے میں تحقیق تلاش کریں", "مشین لرننگ", None, False, None, False),
        ("ابحث عن تعلم الآلة", "تعلم الآلة", None, False, None, False),
        ("कृपया मशीन लर्निंग पेपर खोजें", "मशीन लर्निंग", None, False, None, False),
        ("मुझे कैंसर के बारे में शोध खोजो", "कैंसर", None, False, None, False),
        ("请帮我搜索机器学习论文", "机器学习", None, False, None, False),
        ("por favor busca artículos sobre salud", "salud", None, False, None, False),
        ("bonjour recherche des articles sur l'apprentissage automatique", "l'apprentissage automatique", None, False, None, False),
        ("Bitte suche Artikel über maschinelles Lernen", "maschinelles Lernen", None, False, None, False),
    ],
)
def test_conversational_query_cleaning_and_filters(query, expected, year, open_access, author, reviews):
    result = understand_research_query(query)
    assert result.query == expected
    assert result.year_from == year
    assert result.open_access_only is open_access
    assert result.author == author
    assert result.reviews_only is reviews


def test_screenshot_abstract_is_cleaned_and_figure_record_is_rejected():
    paper = PaperRecord(
        paper_id="crossref-example",
        title="Search Personalization Using Machine Learning",
        abstract="Search Personalization Using Machine Learning: <jats:p>Firms use machine learning to personalize search.</jats:p>",
        source="crossref",
    )
    assert paper.abstract == "Firms use machine learning to personalize search."

    figure = PaperRecord(
        paper_id="figure-example",
        title="Figure 6: Search Personalization Using Machine Learning",
        abstract="Research result indexed from crossref.",
        source="crossref",
    )
    assert figure.abstract is None
    assert not FederatedSearchService._is_usable_record(figure)
