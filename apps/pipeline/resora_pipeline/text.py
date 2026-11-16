"""Text utilities shared by the local engine and the Spark jobs.

Everything here is pure Python (plus optional numpy) so the exact same logic runs inside Spark executors
(via mapPartitions / UDFs) and in the single-machine engine used for development and tests.
"""

from __future__ import annotations

import hashlib
import re
import unicodedata
from collections.abc import Iterable

_WORD = re.compile(r"[\w]+", re.UNICODE)
_TAGS = re.compile(r"<[^>]+>")
_SPACES = re.compile(r"\s+")
_DOI = re.compile(r"10\.\d{4,9}/[^\s\"<>]+", re.IGNORECASE)
_ARXIV_NEW = re.compile(r"(?<!\d)(\d{4}\.\d{4,5})(v\d+)?(?!\d)")
_ARXIV_OLD = re.compile(r"([a-z\-]+(?:\.[A-Z]{2})?/\d{7})(v\d+)?", re.IGNORECASE)

# Words that carry no meaning for matching titles or finding topics.
STOPWORDS = frozenset(
    """a an and are as at be by for from has have in into is it its of on or our that the their this to via we with
    using based towards toward through over under between among about across new novel approach study analysis method
    methods paper results result model models""".split()
)


def strip_markup(text: str | None) -> str:
    """Remove HTML/JATS tags and collapse whitespace (Crossref abstracts arrive as JATS XML)."""
    if not text:
        return ""
    cleaned = _TAGS.sub(" ", str(text))
    cleaned = cleaned.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">").replace("&quot;", '"').replace("&#39;", "'")
    return _SPACES.sub(" ", cleaned).strip()


def fold(text: str | None) -> str:
    """Lower-case, strip accents and punctuation: 'Déjà-Vu: A Study' -> 'deja vu a study'."""
    if not text:
        return ""
    normalized = unicodedata.normalize("NFKD", strip_markup(text))
    without_marks = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    return " ".join(_WORD.findall(without_marks.lower()))


def normalize_title(title: str | None) -> str:
    return fold(title)


def tokens(text: str | None, *, drop_stopwords: bool = False) -> list[str]:
    words = fold(text).split()
    return [word for word in words if not drop_stopwords or (word not in STOPWORDS and len(word) > 1)]


def char_shingles(text: str, size: int = 3) -> set[str]:
    compact = text.replace(" ", "_")
    if len(compact) <= size:
        return {compact} if compact else set()
    return {compact[index:index + size] for index in range(len(compact) - size + 1)}


def jaccard(left: set[str], right: set[str]) -> float:
    if not left or not right:
        return 0.0
    return len(left & right) / len(left | right)


def title_similarity(left: str | None, right: str | None) -> float:
    """Max of word-level and character-trigram Jaccard on folded titles (robust to small typos and reordering)."""
    a, b = normalize_title(left), normalize_title(right)
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    word_score = jaccard(set(a.split()), set(b.split()))
    char_score = jaccard(char_shingles(a), char_shingles(b))
    return max(word_score, char_score)


def normalize_doi(value: str | None) -> str | None:
    if not value:
        return None
    match = _DOI.search(str(value).strip())
    if not match:
        return None
    doi = match.group(0).lower().rstrip(".,;)")
    return doi


def is_arxiv_doi(doi: str | None) -> bool:
    return bool(doi and doi.startswith("10.48550/arxiv."))


def normalize_arxiv_id(value: str | None) -> str | None:
    """'arXiv:2101.00001v3' / 'http://arxiv.org/abs/2101.00001' / '10.48550/arXiv.2101.00001' -> '2101.00001'."""
    if not value:
        return None
    text = str(value).strip()
    match = _ARXIV_NEW.search(text)
    if match:
        return match.group(1)
    match = _ARXIV_OLD.search(text)
    if match and ("arxiv" in text.lower() or "/" in match.group(1)):
        return match.group(1).lower()
    return None


def author_last_name(name: str | None) -> str:
    """Family name used for author matching: 'Li, Wei' -> 'li'; 'Wei Li' -> 'li'; 'A. Rahman' -> 'rahman'."""
    if not name:
        return ""
    text = strip_markup(name)
    if "," in text:
        family = text.split(",", 1)[0]
    else:
        parts = text.split()
        family = parts[-1] if parts else ""
    return fold(family).replace(" ", "")


def stable_id(prefix: str, *parts: object, length: int = 16) -> str:
    digest = hashlib.sha1("␟".join(str(part) for part in parts).encode("utf-8")).hexdigest()
    return f"{prefix}{digest[:length]}"


# --------------------------------------------------------------------------- MinHash (for LSH blocking)

_PRIME = (1 << 31) - 1


def _hash32(value: str) -> int:
    return int.from_bytes(hashlib.blake2b(value.encode("utf-8"), digest_size=4).digest(), "big") % _PRIME


class MinHasher:
    """MinHash signatures with banded LSH. num_perm = bands * rows.

    Two titles with Jaccard similarity s share at least one band with probability 1 - (1 - s^rows)^bands; with the
    defaults (16 bands x 4 rows) that is ~0.98 at s=0.7 and ~0.06 at s=0.3, so near-duplicates are almost always
    compared and unrelated titles almost never are.
    """

    def __init__(self, bands: int = 16, rows: int = 4, seed: int = 1729) -> None:
        import random

        self.bands = bands
        self.rows = rows
        self.num_perm = bands * rows
        rng = random.Random(seed)
        self._a = [rng.randrange(1, _PRIME) for _ in range(self.num_perm)]
        self._b = [rng.randrange(0, _PRIME) for _ in range(self.num_perm)]
        try:
            import numpy as np

            self._np = np
            self._a_np = np.array(self._a, dtype=np.uint64)
            self._b_np = np.array(self._b, dtype=np.uint64)
        except ImportError:  # pragma: no cover - numpy is optional
            self._np = None

    def signature(self, shingles: Iterable[str]) -> list[int]:
        hashes = [_hash32(shingle) for shingle in shingles]
        if not hashes:
            return [_PRIME] * self.num_perm
        if self._np is not None:
            np = self._np
            values = np.array(hashes, dtype=np.uint64)[:, None]
            permuted = (values * self._a_np[None, :] + self._b_np[None, :]) % np.uint64(_PRIME)
            return permuted.min(axis=0).astype(np.int64).tolist()
        return [min((a * value + b) % _PRIME for value in hashes) for a, b in zip(self._a, self._b)]

    def band_keys(self, signature: list[int]) -> list[str]:
        keys = []
        for band in range(self.bands):
            chunk = signature[band * self.rows:(band + 1) * self.rows]
            keys.append(f"{band}:{hashlib.blake2b(repr(chunk).encode(), digest_size=8).hexdigest()}")
        return keys
