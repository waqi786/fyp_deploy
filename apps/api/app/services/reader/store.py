"""Reader documents on disk: the original PDF (when there is one), its page texts, metadata and caches.

Privacy:
  * an uploaded PDF belongs to the person who uploaded it (its id mixes in their key; other people get 404);
  * an open-access paper is public text: one copy is shared by everyone who opens it;
  * nothing here is ever sent to an AI provider by itself — see intelligence.py for the user-content rules.
Layout: <READER_STORAGE_DIR>/<id>/meta.json, pages.json, original.pdf, cache/*.json
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import threading
import time
from pathlib import Path
from typing import Any

from app.schemas.reader import ReaderCaption, ReaderDocument
from app.services.reader.pdf_text import PdfText, find_captions

ID_PATTERN = re.compile(r"^[a-f0-9]{24}$")


class DocumentNotFound(LookupError):
    pass


class ReaderStore:
    def __init__(self, root: str | os.PathLike[str] | None = None):
        self.root = Path(root or os.getenv("READER_STORAGE_DIR", "storage/reader"))
        self._lock = threading.Lock()

    # ------------------------------------------------------------------ ids
    @staticmethod
    def upload_id(owner_key: str, data: bytes) -> str:
        digest = hashlib.sha256(data).hexdigest()
        return hashlib.sha256(f"upload:{owner_key}:{digest}".encode()).hexdigest()[:24]

    @staticmethod
    def public_id(data: bytes | None, fallback: str) -> str:
        basis = hashlib.sha256(data).hexdigest() if data else fallback
        return hashlib.sha256(f"public:{basis}".encode()).hexdigest()[:24]

    def _dir(self, doc_id: str) -> Path:
        if not ID_PATTERN.match(doc_id):
            raise DocumentNotFound(doc_id)
        return self.root / doc_id

    # ------------------------------------------------------------------ write
    def save(
        self,
        doc_id: str,
        *,
        owner_key: str | None,
        meta: dict[str, Any],
        text: PdfText | None,
        pages: list[str] | None = None,
        pdf: bytes | None = None,
    ) -> ReaderDocument:
        folder = self._dir(doc_id)
        page_texts = text.pages if text else (pages or [])
        words = sum(len(page.split()) for page in page_texts)
        record = {
            **meta,
            "id": doc_id,
            "owner_key": owner_key,  # None = public
            "has_pdf": pdf is not None,
            "page_count": len(page_texts),
            "word_count": words,
            "reading_minutes": max(1, math.ceil(words / 220)),
            "scanned_pages": text.scanned_pages if text else [],
            "captions": find_captions(page_texts),
            "created_at": time.time(),
        }
        with self._lock:
            folder.mkdir(parents=True, exist_ok=True)
            (folder / "pages.json").write_text(json.dumps(page_texts, ensure_ascii=False), encoding="utf-8")
            if pdf is not None:
                (folder / "original.pdf").write_bytes(pdf)
            self._write_json(folder / "meta.json", record)
        return self._document(record)

    @staticmethod
    def _write_json(path: Path, data: Any) -> None:
        temporary = path.with_suffix(".tmp")
        temporary.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        temporary.replace(path)

    # ------------------------------------------------------------------ read
    def exists(self, doc_id: str) -> bool:
        try:
            return (self._dir(doc_id) / "meta.json").exists()
        except DocumentNotFound:
            return False

    def _meta(self, doc_id: str, viewer_key: str) -> dict[str, Any]:
        path = self._dir(doc_id) / "meta.json"
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise DocumentNotFound(doc_id) from error
        owner = record.get("owner_key")
        if owner and owner != viewer_key:
            raise DocumentNotFound(doc_id)  # never reveal that a private document exists
        return record

    def get(self, doc_id: str, viewer_key: str) -> ReaderDocument:
        return self._document(self._meta(doc_id, viewer_key))

    def is_private(self, doc_id: str, viewer_key: str) -> bool:
        return bool(self._meta(doc_id, viewer_key).get("owner_key"))

    def pages(self, doc_id: str, viewer_key: str) -> list[str]:
        self._meta(doc_id, viewer_key)
        try:
            return json.loads((self._dir(doc_id) / "pages.json").read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise DocumentNotFound(doc_id) from error

    def pdf_path(self, doc_id: str, viewer_key: str) -> Path:
        self._meta(doc_id, viewer_key)
        path = self._dir(doc_id) / "original.pdf"
        if not path.exists():
            raise DocumentNotFound(doc_id)
        return path

    # ------------------------------------------------------------------ caches
    def cache_get(self, doc_id: str, key: str) -> Any | None:
        path = self._dir(doc_id) / "cache" / f"{hashlib.sha1(key.encode()).hexdigest()[:20]}.json"
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None

    def cache_put(self, doc_id: str, key: str, value: Any) -> None:
        folder = self._dir(doc_id) / "cache"
        folder.mkdir(parents=True, exist_ok=True)
        self._write_json(folder / f"{hashlib.sha1(key.encode()).hexdigest()[:20]}.json", value)

    @staticmethod
    def _document(record: dict[str, Any]) -> ReaderDocument:
        return ReaderDocument(
            id=record["id"],
            title=record.get("title") or "Untitled document",
            authors=record.get("authors") or [],
            year=record.get("year"),
            venue=record.get("venue"),
            doi=record.get("doi"),
            url=record.get("url"),
            abstract=record.get("abstract"),
            source=record.get("source", "upload"),
            has_pdf=bool(record.get("has_pdf")),
            page_count=int(record.get("page_count") or 0),
            word_count=int(record.get("word_count") or 0),
            reading_minutes=int(record.get("reading_minutes") or 1),
            scanned_pages=record.get("scanned_pages") or [],
            captions=[ReaderCaption(**item) for item in record.get("captions") or []],
            is_open_access=bool(record.get("is_open_access")),
            citation_count=int(record.get("citation_count") or 0),
        )


_store: ReaderStore | None = None


def get_reader_store() -> ReaderStore:
    global _store
    if _store is None:
        _store = ReaderStore()
    return _store
