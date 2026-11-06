import asyncio
import os

import pytest

from app.schemas.search import SearchFilters, SourceSearchRequest
from app.services.search.crossref_service import CrossrefProvider
from app.services.search.openalex_service import OpenAlexProvider


pytestmark = pytest.mark.integration


def _integration_enabled() -> bool:
    return os.getenv("RESORA_RUN_INTEGRATION") == "1"


@pytest.mark.skipif(not _integration_enabled(), reason="Set RESORA_RUN_INTEGRATION=1 to run live API integration tests.")
def test_openalex_live_search_returns_normalized_records() -> None:
    request = SourceSearchRequest(query="hybrid retrieval", limit=3, filters=SearchFilters())

    papers = asyncio.run(OpenAlexProvider().search(request))

    assert papers
    assert all(paper.source == "openalex" for paper in papers)
    assert all(paper.title for paper in papers)


@pytest.mark.skipif(not _integration_enabled(), reason="Set RESORA_RUN_INTEGRATION=1 to run live API integration tests.")
def test_crossref_live_search_returns_normalized_records() -> None:
    request = SourceSearchRequest(query="literature review", limit=3, filters=SearchFilters())

    papers = asyncio.run(CrossrefProvider().search(request))

    assert papers
    assert all(paper.source == "crossref" for paper in papers)
    assert all(paper.title for paper in papers)
