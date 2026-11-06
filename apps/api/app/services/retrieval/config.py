from dataclasses import dataclass


@dataclass(frozen=True)
class RetrievalConfig:
    chunk_size: int = 1200
    chunk_overlap: int = 200
    bm25_weight: float = 0.4
    dense_weight: float = 0.6
    temperature: float = 0.0


DEFAULT_RETRIEVAL_CONFIG = RetrievalConfig()
