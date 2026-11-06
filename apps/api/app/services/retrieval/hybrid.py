import math
import re
import time
from collections import Counter, defaultdict
from dataclasses import dataclass

from app.services.retrieval.chunking import make_chunk_id, split_text
from app.services.retrieval.config import DEFAULT_RETRIEVAL_CONFIG
from app.services.retrieval.vector_store import FaissLiteStore


TOKEN_PATTERN = re.compile(r"\b[\w-]+\b", re.UNICODE)


def tokenize(text: str) -> list[str]:
    return [token.lower() for token in TOKEN_PATTERN.findall(text)]


@dataclass
class IndexedChunk:
    chunk_id: str
    paper_id: str
    title: str
    text: str


@dataclass
class RetrievalHit:
    chunk_id: str
    paper_id: str
    title: str
    text: str
    score: float


@dataclass
class IndexingVerification:
    expected_chunks: int
    indexed_chunks: int
    missing_chunk_ids: list[str]
    verified: bool


class HybridRetriever:
    def __init__(self) -> None:
        self._chunks: dict[str, IndexedChunk] = {}
        self._chunk_tokens: dict[str, Counter[str]] = {}
        self._paper_chunks_cache: dict[str, list[str]] = {}
        self._doc_freq: defaultdict[str, int] = defaultdict(int)
        self._token_count: dict[str, int] = {}
        self._vector_store = FaissLiteStore()
        self._indexed_chunk_ids: set[str] = set()

    def index_documents(self, documents: list[dict[str, str]]) -> int:
        for document in documents:
            paper_id = document["paper_id"]
            title = document["title"]
            multimodal_segments = [document["content"]]
            for figure in document.get("figures", []):
                multimodal_segments.append(f"Figure {figure.get('figure_id', '')}: {figure.get('caption', '')}. {figure.get('description', '')}")
            for table in document.get("tables", []):
                multimodal_segments.append(f"Table {table.get('table_id', '')}: {table.get('caption', '')}. {table.get('summary', '')}")
            for equation in document.get("equations", []):
                multimodal_segments.append(f"Equation: {equation}")
            composed = "\n".join(segment for segment in multimodal_segments if segment)
            paper_chunks = split_text(composed, DEFAULT_RETRIEVAL_CONFIG.chunk_size, DEFAULT_RETRIEVAL_CONFIG.chunk_overlap)
            self._paper_chunks_cache[paper_id] = paper_chunks
            for chunk in paper_chunks:
                chunk_id = make_chunk_id(paper_id, chunk)
                if chunk_id in self._chunks:
                    continue
                tokens = Counter(tokenize(chunk))
                self._chunks[chunk_id] = IndexedChunk(chunk_id=chunk_id, paper_id=paper_id, title=title, text=chunk)
                self._chunk_tokens[chunk_id] = tokens
                self._token_count[chunk_id] = sum(tokens.values())
                self._vector_store.add(chunk_id, chunk)
                self._indexed_chunk_ids.add(chunk_id)
                for token in tokens:
                    self._doc_freq[token] += 1
        return len(self._chunks)

    def expected_chunk_ids(self, documents: list[dict[str, str]]) -> list[str]:
        expected: list[str] = []
        for document in documents:
            multimodal_segments = [document["content"]]
            for figure in document.get("figures", []):
                multimodal_segments.append(f"Figure {figure.get('figure_id', '')}: {figure.get('caption', '')}. {figure.get('description', '')}")
            for table in document.get("tables", []):
                multimodal_segments.append(f"Table {table.get('table_id', '')}: {table.get('caption', '')}. {table.get('summary', '')}")
            for equation in document.get("equations", []):
                multimodal_segments.append(f"Equation: {equation}")
            composed = "\n".join(segment for segment in multimodal_segments if segment)
            for chunk in split_text(composed, DEFAULT_RETRIEVAL_CONFIG.chunk_size, DEFAULT_RETRIEVAL_CONFIG.chunk_overlap):
                expected.append(make_chunk_id(document["paper_id"], chunk))
        return expected

    def verify_indexed_chunks(self, expected_chunk_ids: list[str]) -> IndexingVerification:
        missing = [chunk_id for chunk_id in expected_chunk_ids if chunk_id not in self._indexed_chunk_ids]
        return IndexingVerification(
            expected_chunks=len(expected_chunk_ids),
            indexed_chunks=len(expected_chunk_ids) - len(missing),
            missing_chunk_ids=missing,
            verified=not missing,
        )

    def wait_until_indexed(self, expected_chunks: int, timeout_seconds: float = 2.0, expected_chunk_ids: list[str] | None = None) -> bool:
        deadline = time.time() + timeout_seconds
        while time.time() < deadline:
            if expected_chunk_ids:
                if self.verify_indexed_chunks(expected_chunk_ids).verified:
                    return True
            elif len(self._chunks) >= expected_chunks:
                return True
            time.sleep(0.05)
        if expected_chunk_ids:
            return self.verify_indexed_chunks(expected_chunk_ids).verified
        return len(self._chunks) >= expected_chunks

    def retrieve(self, query: str, top_k: int = 5) -> list[RetrievalHit]:
        bm25_ranked = self.retrieve_bm25(query, top_k * 2)
        dense_ranked = self.retrieve_dense(query, top_k * 2)
        return self._rrf_fuse(bm25_ranked, dense_ranked, top_k)

    def retrieve_bm25(self, query: str, top_k: int = 5) -> list[RetrievalHit]:
        return self._bm25(query, top_k)

    def retrieve_dense(self, query: str, top_k: int = 5) -> list[RetrievalHit]:
        return self._dense(query, top_k)

    def _bm25(self, query: str, top_k: int) -> list[RetrievalHit]:
        query_tokens = tokenize(query)
        scores: list[RetrievalHit] = []
        total_docs = max(len(self._chunks), 1)
        avgdl = sum(self._token_count.values()) / total_docs if total_docs else 0
        k1 = 1.5
        b = 0.75
        for chunk_id, chunk in self._chunks.items():
            tokens = self._chunk_tokens[chunk_id]
            dl = self._token_count.get(chunk_id, 0) or 1
            score = 0.0
            for token in query_tokens:
                tf = tokens.get(token, 0)
                if tf == 0:
                    continue
                df = self._doc_freq.get(token, 0)
                idf = math.log(1 + ((total_docs - df + 0.5) / (df + 0.5)))
                numerator = tf * (k1 + 1)
                denominator = tf + k1 * (1 - b + b * (dl / max(avgdl, 1)))
                score += idf * (numerator / denominator)
            if score > 0:
                scores.append(RetrievalHit(chunk_id=chunk_id, paper_id=chunk.paper_id, title=chunk.title, text=chunk.text, score=score))
        return sorted(scores, key=lambda item: item.score, reverse=True)[:top_k]

    def _dense(self, query: str, top_k: int) -> list[RetrievalHit]:
        scores: list[RetrievalHit] = []
        for hit in self._vector_store.search(query, top_k):
            chunk = self._chunks[hit.chunk_id]
            scores.append(
                RetrievalHit(
                    chunk_id=hit.chunk_id,
                    paper_id=chunk.paper_id,
                    title=chunk.title,
                    text=chunk.text,
                    score=hit.score,
                )
            )
        return scores

    def _rrf_fuse(self, bm25_ranked: list[RetrievalHit], dense_ranked: list[RetrievalHit], top_k: int) -> list[RetrievalHit]:
        k = 60
        weighted_scores: defaultdict[str, float] = defaultdict(float)
        merged: dict[str, RetrievalHit] = {}
        for weight, ranked in (
            (DEFAULT_RETRIEVAL_CONFIG.bm25_weight, bm25_ranked),
            (DEFAULT_RETRIEVAL_CONFIG.dense_weight, dense_ranked),
        ):
            for rank, hit in enumerate(ranked, start=1):
                weighted_scores[hit.chunk_id] += weight * (1 / (k + rank))
                merged[hit.chunk_id] = hit
        fused = [
            RetrievalHit(
                chunk_id=chunk_id,
                paper_id=merged[chunk_id].paper_id,
                title=merged[chunk_id].title,
                text=merged[chunk_id].text,
                score=score,
            )
            for chunk_id, score in weighted_scores.items()
        ]
        return sorted(fused, key=lambda item: item.score, reverse=True)[:top_k]


def cosine_similarity(left: Counter[str], right: Counter[str]) -> float:
    common = set(left) & set(right)
    numerator = sum(left[token] * right[token] for token in common)
    left_norm = math.sqrt(sum(value * value for value in left.values()))
    right_norm = math.sqrt(sum(value * value for value in right.values()))
    if not left_norm or not right_norm:
        return 0.0
    return numerator / (left_norm * right_norm)
