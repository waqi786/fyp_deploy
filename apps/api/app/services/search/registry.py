from app.services.search.arxiv_service import ArxivProvider
from app.services.search.catalog_sources import (
    DblpProvider,
    DoajProvider,
    EuropePMCProvider,
    HalProvider,
    PreprintProvider,
    ZenodoProvider,
)
from app.services.search.core_service import CoreProvider
from app.services.search.crossref_service import CrossrefProvider
from app.services.search.openalex_service import OpenAlexProvider
from app.services.search.semantic_scholar_service import SemanticScholarProvider


def build_search_provider_registry() -> dict[str, object]:
    return {
        "openalex": OpenAlexProvider(),
        "semantic_scholar": SemanticScholarProvider(),
        "crossref": CrossrefProvider(),
        "arxiv": ArxivProvider(),
        "core": CoreProvider(),
        "europe_pmc": EuropePMCProvider(),
        "doaj": DoajProvider(),
        "dblp": DblpProvider(),
        "zenodo": ZenodoProvider(),
        "preprints": PreprintProvider(),
        "hal": HalProvider(),
    }
