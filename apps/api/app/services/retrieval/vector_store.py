import math
import re
from dataclasses import dataclass

TOKEN_PATTERN = re.compile(r"\b[\w-]+\b", re.UNICODE)
SEMANTIC_ALIASES = {
    "academic": ["scholarly", "research"],
    "question": ["query"],
    "answering": ["qa"],
    "connect": ["links", "connector"],
    "community": ["communities"],
    "gene": ["genomic", "transcriptomic"],
    "expression": ["transcriptomic"],
    "citation": ["reference"],
    "graph": ["network"],
    "bridge": ["connector", "connection"],
    "ranking": ["retrieval"],
    "semantic": ["meaning"],
}


def tokenize(text: str) -> list[str]:
    return [token.lower() for token in TOKEN_PATTERN.findall(text)]


def normalize_token(token: str) -> str:
    normalized = token.lower()
    if normalized.endswith("ies") and len(normalized) > 4:
        return normalized[:-3] + "y"
    if normalized.endswith("ing") and len(normalized) > 5:
        return normalized[:-3]
    if normalized.endswith("ed") and len(normalized) > 4:
        return normalized[:-2]
    if normalized.endswith("s") and len(normalized) > 3:
        return normalized[:-1]
    return normalized


def semantic_counts(text: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for raw_token in tokenize(text):
        token = normalize_token(raw_token)
        counts[token] = counts.get(token, 0) + 1
        for alias in SEMANTIC_ALIASES.get(token, []):
            counts[alias] = counts.get(alias, 0) + 1
    return counts


def cosine_similarity(left: dict[str, int], right: dict[str, int]) -> float:
    common = set(left) & set(right)
    numerator = sum(left[token] * right[token] for token in common)
    left_norm = math.sqrt(sum(value * value for value in left.values()))
    right_norm = math.sqrt(sum(value * value for value in right.values()))
    if not left_norm or not right_norm:
        return 0.0
    return numerator / (left_norm * right_norm)


@dataclass
class VectorHit:
    chunk_id: str
    score: float


class FaissLiteStore:
    def __init__(self) -> None:
        self._vectors: dict[str, dict[str, int]] = {}

    def add(self, chunk_id: str, text: str) -> None:
        self._vectors[chunk_id] = semantic_counts(text)

    def search(self, query: str, top_k: int = 5) -> list[VectorHit]:
        query_counts = semantic_counts(query)
        hits = [
            VectorHit(chunk_id=chunk_id, score=cosine_similarity(query_counts, vector))
            for chunk_id, vector in self._vectors.items()
        ]
        return [hit for hit in sorted(hits, key=lambda item: item.score, reverse=True)[:top_k] if hit.score > 0]
