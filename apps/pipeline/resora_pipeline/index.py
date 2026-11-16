"""Search index over curated papers: semantic vectors (FAISS) + keyword BM25, fused with Reciprocal Rank Fusion.

Semantic side
  * Embedder "hash-v1" (default): signed feature hashing of unigrams + bigrams + character 4-grams into 384 dims,
    L2-normalized. Deterministic, multilingual-safe, no model download, and good at near-synonyms/morphology.
  * Embedder "st:<model>": sentence-transformers (e.g. st:all-MiniLM-L6-v2) when installed — real semantic vectors.
  * Index: FAISS IndexFlatIP (exact cosine) up to 50k papers, IndexIVFFlat above that; numpy fallback without FAISS.

Keyword side
  * BM25 (k1=1.5, b=0.75) over title (weighted ×3), topics (×2) and abstract.

Fusion
  * RRF: score = Σ 1 / (60 + rank_i). Robust to the very different score scales of BM25 and cosine, and each hit
    records which side found it (keyword / semantic / both) so the UI can explain the match.

Files written to <output>/index/: vectors.npy, ids.json, faiss.index (if FAISS), manifest.json.
"""

from __future__ import annotations

import hashlib
import json
import math
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from resora_pipeline.text import fold, tokens

DIM = 384
RRF_K = 60


def _bucket(feature: str) -> tuple[int, float]:
    digest = hashlib.blake2b(feature.encode("utf-8"), digest_size=8).digest()
    value = int.from_bytes(digest, "big")
    return value % DIM, (1.0 if (value >> 63) & 1 else -1.0)


def hash_embed(text: str) -> list[float]:
    words = tokens(text, drop_stopwords=True)
    features: Counter[str] = Counter()
    for word in words:
        features[f"w:{word}"] += 1.0
        padded = f"#{word}#"
        for index in range(max(1, len(padded) - 3)):
            features[f"c:{padded[index:index + 4]}"] += 0.35
    for left, right in zip(words, words[1:]):
        features[f"b:{left}_{right}"] += 0.8
    vector = [0.0] * DIM
    for feature, weight in features.items():
        bucket, sign = _bucket(feature)
        vector[bucket] += sign * (1.0 + math.log(weight)) if weight >= 1 else sign * weight
    norm = math.sqrt(sum(value * value for value in vector)) or 1.0
    return [value / norm for value in vector]


class Embedder:
    def __init__(self, name: str = "hash-v1") -> None:
        self.name = name
        self.model = None
        if name.startswith("st:"):
            from sentence_transformers import SentenceTransformer  # optional dependency

            self.model = SentenceTransformer(name[3:])

    @property
    def dim(self) -> int:
        return self.model.get_sentence_embedding_dimension() if self.model is not None else DIM

    def embed(self, texts: list[str]):  # noqa: ANN201 - returns numpy array
        import numpy as np

        if self.model is not None:
            return np.asarray(self.model.encode(texts, normalize_embeddings=True, batch_size=64), dtype="float32")
        return np.asarray([hash_embed(text) for text in texts], dtype="float32")


def paper_text(paper: dict[str, Any]) -> str:
    return " ".join([paper.get("title") or "", paper.get("title") or "", " ".join(paper.get("topics") or []), (paper.get("abstract") or "")[:2000]])


class BM25:
    def __init__(self, documents: list[list[str]], k1: float = 1.5, b: float = 0.75) -> None:
        self.k1, self.b = k1, b
        self.docs = documents
        self.lengths = [len(doc) for doc in documents]
        self.avg = (sum(self.lengths) / len(documents)) if documents else 0.0
        self.postings: dict[str, list[tuple[int, int]]] = defaultdict(list)
        for index, doc in enumerate(documents):
            for term, count in Counter(doc).items():
                self.postings[term].append((index, count))
        total = len(documents)
        self.idf = {term: math.log(1 + (total - len(post) + 0.5) / (len(post) + 0.5)) for term, post in self.postings.items()}

    def search(self, query_terms: list[str], top_k: int) -> list[tuple[int, float]]:
        scores: dict[int, float] = defaultdict(float)
        for term in set(query_terms):
            idf = self.idf.get(term)
            if idf is None:
                continue
            for index, count in self.postings[term]:
                norm = 1 - self.b + self.b * (self.lengths[index] / self.avg if self.avg else 1)
                scores[index] += idf * count * (self.k1 + 1) / (count + self.k1 * norm)
        return sorted(scores.items(), key=lambda item: (-item[1], item[0]))[:top_k]


def keyword_terms(paper: dict[str, Any]) -> list[str]:
    title = tokens(paper.get("title"), drop_stopwords=True)
    topic_terms = [word for topic in paper.get("topics") or [] for word in tokens(topic, drop_stopwords=True)]
    return title * 3 + topic_terms * 2 + tokens((paper.get("abstract") or "")[:4000], drop_stopwords=True)


class HybridIndex:
    def __init__(self, papers: list[dict[str, Any]], embedder: Embedder, vectors: Any = None, faiss_index: Any = None) -> None:
        import numpy as np

        self.papers = papers
        self.ids = [paper["paper_id"] for paper in papers]
        self.embedder = embedder
        self.vectors = vectors if vectors is not None else (embedder.embed([paper_text(p) for p in papers]) if papers else np.zeros((0, embedder.dim), dtype="float32"))
        self.bm25 = BM25([keyword_terms(paper) for paper in papers])
        self.faiss = faiss_index if faiss_index is not None else self._build_faiss()

    def _build_faiss(self):  # noqa: ANN202
        try:
            import faiss
        except ImportError:
            return None
        count, dim = self.vectors.shape
        if count == 0:
            return None
        if count > 50_000:
            nlist = int(math.sqrt(count))
            quantizer = faiss.IndexFlatIP(dim)
            index = faiss.IndexIVFFlat(quantizer, dim, nlist, faiss.METRIC_INNER_PRODUCT)
            index.train(self.vectors)
            index.nprobe = max(8, nlist // 16)
        else:
            index = faiss.IndexFlatIP(dim)
        index.add(self.vectors)
        return index

    def semantic(self, query: str, top_k: int) -> list[tuple[int, float]]:
        import numpy as np

        if not self.ids:
            return []
        vector = self.embedder.embed([query])
        if self.faiss is not None:
            scores, indices = self.faiss.search(vector, min(top_k, len(self.ids)))
            return [(int(i), float(s)) for i, s in zip(indices[0], scores[0]) if i >= 0]
        sims = self.vectors @ vector[0]
        order = np.argsort(-sims)[:top_k]
        return [(int(i), float(sims[i])) for i in order]

    def search(self, query: str, *, top_k: int = 20, min_semantic: float = 0.12) -> list[dict[str, Any]]:
        if not fold(query):
            return []
        depth = max(top_k * 3, 50)
        keyword = self.bm25.search(tokens(query, drop_stopwords=True) or tokens(query), depth)
        semantic = [(index, score) for index, score in self.semantic(query, depth) if score >= min_semantic]
        fused: dict[int, dict[str, Any]] = {}
        for side, ranked in (("keyword", keyword), ("semantic", semantic)):
            for rank, (index, score) in enumerate(ranked, start=1):
                entry = fused.setdefault(index, {"score": 0.0, "matched": [], "keyword_score": None, "semantic_score": None})
                entry["score"] += 1.0 / (RRF_K + rank)
                entry["matched"].append(side)
                entry[f"{side}_score"] = round(score, 4)
        ordered = sorted(fused.items(), key=lambda item: (-item[1]["score"], item[0]))[:top_k]
        return [{"paper_id": self.ids[index], "score": round(entry["score"], 6), "matched": entry["matched"], "keyword_score": entry["keyword_score"], "semantic_score": entry["semantic_score"]} for index, entry in ordered]

    # ----------------------------------------------------------------- persistence
    def save(self, directory: Path) -> dict[str, Any]:
        import numpy as np

        directory.mkdir(parents=True, exist_ok=True)
        np.save(directory / "vectors.npy", self.vectors)
        (directory / "ids.json").write_text(json.dumps(self.ids), encoding="utf-8")
        has_faiss = False
        if self.faiss is not None:
            import faiss

            faiss.write_index(self.faiss, str(directory / "faiss.index"))
            has_faiss = True
        manifest = {"embedder": self.embedder.name, "dim": int(self.vectors.shape[1]) if self.vectors.size else self.embedder.dim, "papers": len(self.ids), "faiss": has_faiss, "rrf_k": RRF_K, "format": 1}
        (directory / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        return manifest

    @classmethod
    def load(cls, directory: Path, papers_by_id: dict[str, dict[str, Any]]) -> HybridIndex:
        import numpy as np

        manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
        ids = json.loads((directory / "ids.json").read_text(encoding="utf-8"))
        vectors = np.load(directory / "vectors.npy")
        keep = [index for index, paper_id in enumerate(ids) if paper_id in papers_by_id]
        papers = [papers_by_id[ids[index]] for index in keep]
        vectors = vectors[keep] if len(keep) != len(ids) else vectors
        faiss_index = None
        if manifest.get("faiss") and len(keep) == len(ids):
            try:
                import faiss

                faiss_index = faiss.read_index(str(directory / "faiss.index"))
            except ImportError:
                faiss_index = None
        return cls(papers, Embedder(manifest.get("embedder", "hash-v1")), vectors=vectors, faiss_index=faiss_index)
