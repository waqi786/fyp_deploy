from __future__ import annotations

import json

import httpx
import pytest

from resora_pipeline import analytics as A
from resora_pipeline.catalog_db import CatalogDB
from resora_pipeline.collectors.sources import ArxivCollector, CrossrefCollector, OpenAlexCollector, SemanticScholarCollector
from resora_pipeline.dedup import deduplicate, match_rule
from resora_pipeline.index import Embedder, HybridIndex, hash_embed
from resora_pipeline.lake import ObjectStore, LocalStorage
from resora_pipeline.normalize import normalize_envelope
from resora_pipeline.orchestrator import Pipeline
from resora_pipeline.text import MinHasher, normalize_arxiv_id, normalize_doi, title_similarity

from conftest import write_corpus


# ---------------------------------------------------------------- text + normalization

def test_identifier_normalization():
    assert normalize_doi("https://doi.org/10.1234/ABC.5.") == "10.1234/abc.5"
    assert normalize_doi("not a doi") is None
    assert normalize_arxiv_id("http://arxiv.org/abs/2101.00001v3") == "2101.00001"
    assert normalize_arxiv_id("10.48550/arXiv.2101.00001") == "2101.00001"
    assert normalize_arxiv_id("hep-th/9901001v2") == "hep-th/9901001"
    assert title_similarity("Déjà Vu: A Study of X", "deja vu a study of x") == 1.0


def test_every_source_normalizes_to_one_schema(corpus):
    seen = set()
    for _, envelopes in corpus:
        for envelope in envelopes:
            record = normalize_envelope(envelope)
            assert record is not None, envelope["source"]
            assert record["title_norm"] and record["record_id"].startswith(envelope["source"] + ":")
            assert set(record) >= {"doi", "arxiv_id", "authors", "topics", "year", "citation_count"}
            seen.add(record["source"])
    assert seen == {"openalex", "crossref", "arxiv", "semantic_scholar"}
    crossref = normalize_envelope({"source": "crossref", "raw": {"DOI": "10.1000/x", "title": ["<i>Hi</i> there friends"], "abstract": "<jats:p>Text &amp; more</jats:p>"}})
    assert crossref["title"] == "Hi there friends" and crossref["abstract"] == "Text & more"
    assert normalize_envelope({"source": "unknown", "raw": {}}) is None
    assert normalize_envelope({"source": "crossref", "raw": {"DOI": "10.1/x", "title": [""]}}) is None


# ---------------------------------------------------------------- deduplication

def test_deduplication_recovers_ground_truth(corpus):
    records = [normalize_envelope(e) for _, envs in corpus for e in envs]
    papers, stats = deduplicate(records)
    assert len(papers) == len(corpus)  # one curated paper per real-world paper, look-alikes kept apart
    by_record = {record_id: p for p in papers for record_id in p["source_records"]}
    for key, envelopes in corpus:
        if key.startswith("10.1234"):
            ids = {normalize_envelope(e)["record_id"] for e in envelopes}
            paper = by_record[next(iter(ids))]
            assert set(paper["source_records"]) == ids
            assert paper["duplicate_count"] == len(envelopes) - 1
            assert sorted(paper["sources"]) == sorted({e["source"] for e in envelopes})
    assert stats.as_dict()["duplicates_merged"] == len(records) - len(corpus)
    assert {"doi", "arxiv"} <= set(stats.by_rule)


def test_merge_prefers_best_metadata(corpus):
    records = [normalize_envelope(e) for _, envs in corpus[:1] for e in envs]  # paper 0: openalex+crossref+arxiv+s2
    (paper,), _ = deduplicate(records)
    assert paper["doi"] == "10.1234/resora.0000" and paper["arxiv_id"]
    assert paper["year"] == 2016  # published year, not the preprint year
    assert "long detailed abstract" in paper["abstract"]  # longest abstract wins
    assert paper["citation_count"] == 3  # max across sources (crossref reported cites + 3)
    assert paper["authors"][0]["orcid"]  # ORCID enriched from OpenAlex
    assert paper["venue"] == "Journal of Scalable AI"


def test_match_rules_reject_false_positives():
    base = {"source": "crossref", "type": "journal-article", "doi": None, "arxiv_id": None, "year": 2020, "title": "Attention is all you need for graphs", "authors": [{"name": "Ana Silva"}]}
    assert match_rule(base, {**base, "source": "openalex", "title": "Attention Is All You Need For Graphs!"}) == "title+authors"
    assert match_rule(base, {**base, "authors": [{"name": "Bo Chen"}]}) is None  # different people
    assert match_rule({**base, "doi": "10.1/a"}, {**base, "doi": "10.1/b"}) is None  # two published DOIs
    assert match_rule(base, {**base, "year": 2015}) is None  # incompatible years
    assert match_rule({**base, "source": "arxiv", "type": "preprint", "year": 2018}, base) == "title+authors"  # preprint 2y earlier


def test_minhash_lsh_finds_near_duplicates_only():
    hasher = MinHasher()
    from resora_pipeline.text import char_shingles

    a = hasher.band_keys(hasher.signature(char_shingles("scalable transformer for computer vision benchmark")))
    b = hasher.band_keys(hasher.signature(char_shingles("scalable transformers for computer vision benchmark")))
    c = hasher.band_keys(hasher.signature(char_shingles("federated learning in medical imaging")))
    assert set(a) & set(b)
    assert not set(a) & set(c)


# ---------------------------------------------------------------- end to end (local engine)

def test_local_pipeline_end_to_end(config, lake, corpus):
    raw = write_corpus(lake, corpus)
    pipeline = Pipeline(config, lake=lake)
    result = pipeline.run(queries=[], sources=[], skip_ingest=True, run_id="run-1")
    etl = result["etl"]
    assert etl["raw_records"] == raw and etl["unique_papers"] == len(corpus) and etl["dropped_invalid"] == 0
    assert pipeline.db.count() == len(corpus)
    runs = pipeline.db.runs()
    assert runs[0]["status"] == "succeeded" and runs[0]["stats"]["etl"]["duplicates_merged"] == raw - len(corpus)
    # idempotent: a second run over the same lake does not create duplicates
    pipeline.run(queries=[], sources=[], skip_ingest=True, run_id="run-2")
    assert pipeline.db.count() == len(corpus)
    analytics = json.loads((config.output_dir / "analytics.json").read_text())
    assert analytics["paper_count"] == len(corpus)
    assert [row["topic"] for row in analytics["topic_trends"]][:1]
    assert analytics["source_coverage"]["duplicates_merged"] == raw - len(corpus)
    assert {event["topic"] for event in pipeline.bus.published} == {"etl.completed", "analytics.completed", "index.completed"}
    assert lake.storage.list("events/etl.completed")  # event log in the lake
    manifest = json.loads((config.output_dir / "index" / "manifest.json").read_text())
    assert manifest["papers"] == len(corpus) and manifest["embedder"] == "hash-v1"


def test_hybrid_search_combines_keyword_and_semantic(config, lake, corpus):
    write_corpus(lake, corpus)
    pipeline = Pipeline(config, lake=lake)
    papers, _ = pipeline.etl_local(run_id="r")
    index = HybridIndex(papers, Embedder("hash-v1"))
    hits = index.search("federated learning graph neural networks", top_k=5)
    titles = [next(p for p in papers if p["paper_id"] == hit["paper_id"])["title"].lower() for hit in hits]
    assert "federated learning" in titles[0]
    assert "keyword" in hits[0]["matched"] and "semantic" in hits[0]["matched"]
    # morphology: plural/variant still matches semantically through character n-grams
    assert index.search("distillations of knowledges", top_k=3)
    index.save(config.output_dir / "idx")
    reloaded = HybridIndex.load(config.output_dir / "idx", {p["paper_id"]: p for p in papers})
    assert reloaded.search("federated learning graph neural networks", top_k=1)[0]["paper_id"] == hits[0]["paper_id"]
    assert len(hash_embed("x y z")) == 384


# ---------------------------------------------------------------- analytics

def test_hot_topics_and_gap_candidates_are_evidence_based():
    papers = []
    for i in range(30):
        papers.append({"paper_id": f"a{i}", "year": 2025 if i < 12 else 2018, "topics": ["Diffusion models"] if i < 12 else ["Speech"], "citation_count": i, "sources": ["openalex"], "authors": []})
    for i in range(30):
        papers.append({"paper_id": f"b{i}", "year": 2020, "topics": ["Robotics"] if i % 2 else ["Healthcare"], "citation_count": 0, "sources": ["crossref", "openalex"], "authors": []})
    hot = A.hot_topics(papers, current_year=2026)
    assert hot[0]["topic"] == "Diffusion models" and hot[0]["status"] == "emerging" and hot[0]["example_paper_ids"]
    gaps = A.gap_candidates(papers)
    pair = next(g for g in gaps if set(g["topics"]) == {"Robotics", "Healthcare"})
    assert pair["together"] == 0 and pair["expected"] > 2 and pair["evidence"]["a"]
    coverage = A.source_coverage(papers)
    assert coverage["papers_per_source"]["openalex"] == 60 and coverage["unique_to_source"]["openalex"] == 30


# ---------------------------------------------------------------- collectors (recorded responses, no network)

def _client(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_openalex_collector_cursor_pagination_and_lake_write(config, lake):
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(dict(request.url.params))
        cursor = request.url.params["cursor"]
        if cursor == "*":
            return httpx.Response(200, json={"meta": {"next_cursor": "c2"}, "results": [{"id": "https://openalex.org/W1", "title": "A paper title here"}]})
        return httpx.Response(200, json={"meta": {"next_cursor": None}, "results": [{"id": "https://openalex.org/W2", "title": "Another paper title"}]})

    result = OpenAlexCollector(config, lake, client=_client(handler), sleep=lambda s: None).collect("llm", run_id="r1", max_records=10)
    assert result.records == 2 and len(result.files) == 1
    assert calls[0]["mailto"] == "test@example.org"
    rows = list(lake.read_jsonl(result.files[0]))
    assert rows[0]["source"] == "openalex" and rows[0]["raw"]["id"].endswith("W1")
    # incremental: the next run asks only for records updated since the last success
    OpenAlexCollector(config, lake, client=_client(handler), sleep=lambda s: None).collect("llm", run_id="r2", max_records=1)
    assert calls[-1]["filter"].startswith("from_updated_date:")


def test_collectors_retry_on_429_and_parse_each_api(config, lake):
    attempts = {"n": 0}

    def crossref(request):
        attempts["n"] += 1
        if attempts["n"] == 1:
            return httpx.Response(429, headers={"Retry-After": "0"})
        return httpx.Response(200, json={"message": {"items": [{"DOI": "10.1/a", "title": ["Retry works fine"]}], "next-cursor": None}})

    result = CrossrefCollector(config, lake, client=_client(crossref), sleep=lambda s: None).collect("q", run_id="r", max_records=5)
    assert result.records == 1 and attempts["n"] == 2

    feed = """<feed xmlns="http://www.w3.org/2005/Atom" xmlns:arxiv="http://arxiv.org/schemas/atom"><entry>
      <id>http://arxiv.org/abs/2101.00001v1</id><title>An arXiv   paper</title><summary>Abs</summary>
      <published>2021-01-01T00:00:00Z</published><updated>2021-01-02T00:00:00Z</updated>
      <author><name>Ana Silva</name></author><arxiv:doi>10.1/x</arxiv:doi><category term="cs.LG"/>
      <link title="pdf" href="http://arxiv.org/pdf/2101.00001v1"/></entry></feed>"""
    pages = iter([feed, '<feed xmlns="http://www.w3.org/2005/Atom"></feed>'])
    arxiv = ArxivCollector(config, lake, client=_client(lambda r: httpx.Response(200, text=next(pages))), sleep=lambda s: None)
    arxiv.limiter.rate = 1000
    out = arxiv.collect("q", run_id="r", max_records=50)
    row = next(lake.read_jsonl(out.files[0]))["raw"]
    assert row["title"] == "An arXiv paper" and row["doi"] == "10.1/x" and row["categories"] == ["cs.LG"]

    s2 = SemanticScholarCollector(config, lake, client=_client(lambda r: httpx.Response(200, json={"data": [{"paperId": "p1", "title": "S2 paper title"}], "token": None})), sleep=lambda s: None)
    assert s2.collect("q", run_id="r", max_records=5).records == 1


def test_object_store_checks_pdf_magic_and_is_content_addressed(tmp_path):
    store = ObjectStore(LocalStorage(tmp_path / "objects"))
    ref = store.put_pdf(b"%PDF-1.7 test", paper_id="rp_1")
    assert ref["key"].startswith("pdfs/") and store.get(ref["key"]) == b"%PDF-1.7 test"
    assert store.put_pdf(b"%PDF-1.7 test", paper_id="rp_2")["key"] == ref["key"]
    with pytest.raises(ValueError):
        store.put_pdf(b"<html>", paper_id="x")
    with pytest.raises(ValueError):
        LocalStorage(tmp_path / "objects").put_bytes("../escape", b"x")


def test_catalog_db_upsert_is_idempotent(tmp_path):
    db = CatalogDB(f"sqlite:///{tmp_path / 'c.sqlite3'}")
    paper = {"paper_id": "rp_1", "title": "T", "authors": [{"name": "A"}], "topics": ["x"], "sources": ["openalex"], "source_records": ["openalex:W1"]}
    db.upsert_papers([paper], run_id="r1")
    db.upsert_papers([{**paper, "title": "T2"}], run_id="r2")
    rows = db.papers()
    assert len(rows) == 1 and rows[0]["title"] == "T2" and rows[0]["first_run_id"] == "r1" and rows[0]["authors"] == [{"name": "A"}]
