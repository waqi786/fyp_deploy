from app.services.retrieval.benchmark import (
    RetrievalBenchmarkCase,
    RetrievalBenchmarkService,
)
from app.services.retrieval.hybrid import HybridRetriever


def make_documents() -> list[dict[str, object]]:
    return [
        {
            "paper_id": "paper-0",
            "title": "Academic Ranking Strategies",
            "content": "Academic ranking strategies discuss retrieval evaluation, scholarly search, lexical baselines, and answer quality dashboards without BM25 fusion.",
            "figures": [],
            "tables": [],
            "equations": [],
        },
        {
            "paper_id": "paper-1",
            "title": "Hybrid Retrieval for Academic QA",
            "content": "Hybrid retrieval combines BM25 lexical matching with dense semantic ranking for academic question answering.",
            "figures": [],
            "tables": [],
            "equations": [],
        },
        {
            "paper_id": "paper-2",
            "title": "Gene Expression Clustering",
            "content": "Gene expression clustering groups transcriptomic samples using biological signal and pathway-aware embeddings.",
            "figures": [],
            "tables": [],
            "equations": [],
        },
        {
            "paper_id": "paper-3",
            "title": "Citation Graph Bridges",
            "content": "Bridge nodes in citation graphs connect research communities and improve graph exploration workflows.",
            "figures": [],
            "tables": [],
            "equations": [],
        },
        {
            "paper_id": "paper-4",
            "title": "Research Communities in Networked Systems",
            "content": "Research communities in networked systems discuss communities, links, and connectors, but not citation graphs or bridge nodes.",
            "figures": [],
            "tables": [],
            "equations": [],
        },
    ]


def test_hybrid_retriever_verifies_expected_chunk_ids() -> None:
    retriever = HybridRetriever()
    documents = make_documents()

    expected_chunk_ids = retriever.expected_chunk_ids(documents)
    expected_count = retriever.index_documents(documents)

    assert retriever.wait_until_indexed(expected_count, expected_chunk_ids=expected_chunk_ids) is True
    verification = retriever.verify_indexed_chunks(expected_chunk_ids)
    assert verification.verified is True
    assert verification.expected_chunks == expected_count
    assert verification.missing_chunk_ids == []


def test_retrieval_benchmark_reports_hybrid_at_least_as_good_as_single_methods() -> None:
    service = RetrievalBenchmarkService()
    report = service.evaluate(
        documents=make_documents(),
        cases=[
            RetrievalBenchmarkCase(question="How does question answering with dense bm25 fusion work?", expected_paper_id="paper-1"),
            RetrievalBenchmarkCase(question="Which paper discusses transcriptomic samples and pathway embeddings?", expected_paper_id="paper-2"),
            RetrievalBenchmarkCase(question="What bridge connects reference communities in networks?", expected_paper_id="paper-3"),
        ],
        top_k=1,
    )

    assert report.hybrid.accuracy >= report.bm25.accuracy
    assert report.hybrid.accuracy >= report.dense.accuracy
    assert report.hybrid.accuracy > report.bm25.accuracy or report.hybrid.accuracy > report.dense.accuracy
    assert report.hybrid.hits == report.hybrid.total
