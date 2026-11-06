"""Benchmark helpers for retrieval-quality verification."""

from __future__ import annotations

from dataclasses import dataclass

from app.services.retrieval.hybrid import HybridRetriever


@dataclass
class RetrievalBenchmarkCase:
    question: str
    expected_paper_id: str


@dataclass
class RetrievalBenchmarkResult:
    method: str
    accuracy: float
    hits: int
    total: int


@dataclass
class RetrievalBenchmarkReport:
    bm25: RetrievalBenchmarkResult
    dense: RetrievalBenchmarkResult
    hybrid: RetrievalBenchmarkResult


class RetrievalBenchmarkService:
    """Measures BM25, dense, and hybrid retrieval on the same fixed corpus."""

    def evaluate(
        self,
        *,
        documents: list[dict[str, object]],
        cases: list[RetrievalBenchmarkCase],
        top_k: int = 1,
    ) -> RetrievalBenchmarkReport:
        retriever = HybridRetriever()
        retriever.index_documents(documents)

        return RetrievalBenchmarkReport(
            bm25=self._score("bm25", cases, top_k, retriever.retrieve_bm25),
            dense=self._score("dense", cases, top_k, retriever.retrieve_dense),
            hybrid=self._score("hybrid", cases, top_k, retriever.retrieve),
        )

    def _score(self, method: str, cases: list[RetrievalBenchmarkCase], top_k: int, retriever_fn) -> RetrievalBenchmarkResult:
        hits = 0
        for case in cases:
            results = retriever_fn(case.question, top_k=top_k)
            if any(result.paper_id == case.expected_paper_id for result in results):
                hits += 1
        total = len(cases)
        accuracy = hits / total if total else 0.0
        return RetrievalBenchmarkResult(method=method, accuracy=accuracy, hits=hits, total=total)
