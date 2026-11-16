"""Synthetic but realistic raw corpus: the same papers arrive from several sources with the metadata differences
seen in practice (DOI case/prefix, arXiv versions, punctuation and casing in titles, preprint years, missing
abstracts), plus look-alike papers that must NOT be merged."""

from __future__ import annotations

import random
from pathlib import Path

import pytest

from resora_pipeline.config import PipelineConfig
from resora_pipeline.lake import DataLake, LocalStorage

TOPICS = ["Computer vision", "Natural language processing", "Reinforcement learning", "Medical imaging", "Graph neural networks", "Speech recognition"]
METHODS = ["transformer", "diffusion model", "contrastive learning", "graph attention", "federated learning", "knowledge distillation"]


def make_corpus(seed: int = 7, papers: int = 60):
    rng = random.Random(seed)
    truth = []  # (canonical key, envelopes)
    for n in range(papers):
        method = METHODS[n % len(METHODS)]
        topic_a = TOPICS[n % len(TOPICS)]
        topic_b = TOPICS[(n * 7 + 3) % len(TOPICS)] if n % 4 else topic_a
        title = f"Scalable {method} for {topic_a.lower()} benchmark number {n}"
        year = 2016 + (n % 10)
        doi = f"10.1234/resora.{n:04d}"
        arxiv = f"{2000 + n // 10:04d}.{10000 + n:05d}"
        authors = [f"Author{n} Family{n}", f"Second{n} Coauthor{n % 13}"]
        cites = (n * 37) % 400
        envelopes = []
        if n % 3 != 2:  # OpenAlex has most papers
            envelopes.append({"source": "openalex", "fetched_at": "2026-11-01T00:00:00Z", "raw": {
                "id": f"https://openalex.org/W{9000 + n}", "doi": f"https://doi.org/{doi.upper()}", "title": title,
                "publication_year": year, "type": "article", "cited_by_count": cites, "referenced_works_count": 20,
                "primary_location": {"source": {"display_name": "Journal of Scalable AI"}, "pdf_url": None},
                "authorships": [{"author": {"display_name": a, "orcid": f"https://orcid.org/0000-0000-0000-{n:04d}" if i == 0 else None}, "institutions": [{"display_name": "LUMS" if n % 2 else "Tsinghua University"}]} for i, a in enumerate(authors)],
                "topics": [{"display_name": topic_a}, {"display_name": topic_b}], "open_access": {"is_oa": n % 2 == 0},
                "abstract_inverted_index": {"We": [0], "study": [1], method.split()[0]: [2]},
            }})
        if n % 2 == 0:  # Crossref: same DOI, title with different punctuation/casing
            envelopes.append({"source": "crossref", "fetched_at": "2026-11-01T00:00:00Z", "raw": {
                "DOI": doi, "title": [title.upper().replace(" for ", ": for ")], "issued": {"date-parts": [[year, 3]]},
                "container-title": ["Journal of Scalable AI"], "type": "journal-article", "is-referenced-by-count": cites + 3,
                "author": [{"given": a.split()[0], "family": a.split()[1]} for a in authors], "subject": [topic_a],
                "abstract": f"<jats:p>We study {method} at scale for {topic_a.lower()} with a long detailed abstract.</jats:p>",
            }})
        if n % 5 == 0:  # arXiv preprint one year earlier, no DOI, versioned id
            envelopes.append({"source": "arxiv", "fetched_at": "2026-11-01T00:00:00Z", "raw": {
                "id": f"http://arxiv.org/abs/{arxiv}v2", "title": title + ".", "summary": f"Preprint about {method}.",
                "published": f"{year - 1}-11-02T00:00:00Z", "updated": f"{year}-01-01T00:00:00Z",
                "authors": [{"name": a} for a in authors], "categories": ["cs.LG", "cs.CV"],
            }})
        if n % 3 == 0:  # Semantic Scholar knows both the DOI and the arXiv id
            envelopes.append({"source": "semantic_scholar", "fetched_at": "2026-11-01T00:00:00Z", "raw": {
                "paperId": f"s2-{n}", "externalIds": {"DOI": doi, **({"ArXiv": arxiv} if n % 5 == 0 else {})}, "title": title,
                "year": year, "venue": "J. Scalable AI", "citationCount": cites + 1, "authors": [{"name": a} for a in authors],
                "fieldsOfStudy": ["Computer Science"], "isOpenAccess": True, "openAccessPdf": {"url": f"https://example.org/{n}.pdf"},
            }})
        if not envelopes:
            envelopes.append({"source": "openalex", "fetched_at": "2026-11-01T00:00:00Z", "raw": {"id": f"https://openalex.org/W{9000 + n}", "title": title, "publication_year": year, "authorships": [{"author": {"display_name": a}} for a in authors], "topics": [{"display_name": topic_a}]}})
        rng.shuffle(envelopes)
        truth.append((doi, envelopes))
    # Look-alikes that must stay separate: same generic title, different authors and years; different DOIs.
    for k in range(2):
        truth.append((f"lookalike-{k}", [{"source": "crossref", "fetched_at": "2026-11-01T00:00:00Z", "raw": {
            "DOI": f"10.9999/thesis.{k}", "title": ["Deep learning for image classification"], "issued": {"date-parts": [[2015 + 4 * k]]},
            "author": [{"given": "Unique", "family": f"Person{k}"}], "subject": ["Computer vision"],
        }}]))
    return truth


@pytest.fixture()
def corpus():
    return make_corpus()


@pytest.fixture()
def config(tmp_path: Path) -> PipelineConfig:
    return PipelineConfig(
        lake_uri=(tmp_path / "lake").as_uri(), object_store_uri=(tmp_path / "objects").as_uri(),
        catalog_database_url=f"sqlite:///{tmp_path / 'catalog.sqlite3'}", output_dir=tmp_path / "output", contact_email="test@example.org",
    )


@pytest.fixture()
def lake(config: PipelineConfig) -> DataLake:
    return DataLake(LocalStorage(Path(config.lake_uri.removeprefix("file://"))))


def write_corpus(lake: DataLake, corpus, run_id: str = "run-1") -> int:
    by_source: dict[str, list] = {}
    for _, envelopes in corpus:
        for envelope in envelopes:
            by_source.setdefault(envelope["source"], []).append({**envelope, "run_id": run_id, "query": "test"})
    total = 0
    for source, rows in by_source.items():
        total += lake.write_jsonl(f"{DataLake.raw_prefix(source, '2026-11-01', run_id)}/part-00000.jsonl.gz", rows)
    return total
