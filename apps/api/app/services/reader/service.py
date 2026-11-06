"""Reader service: open a paper (upload, open-access PDF or abstract), then summarize, ask and translate it."""

from __future__ import annotations

import asyncio
import os
from typing import Any

from app.schemas.reader import (
    ReaderAnswer,
    ReaderDocument,
    ReaderPaperRef,
    ReaderSummary,
    TranslateResponse,
)
from app.services.language.config import canonical_language_code
from app.services.reader import fetch, intelligence
from app.services.reader.pdf_text import PdfUnreadable, extract_pdf_text
from app.services.reader.store import DocumentNotFound, ReaderStore, get_reader_store

MAX_UPLOAD_BYTES = int(os.getenv("READER_MAX_PDF_MB", "40")) * 1024 * 1024


class ReaderInputError(ValueError):
    """The input cannot become a readable document (not a PDF, too large, nothing to open)."""


def _language(code: str) -> str:
    try:
        return canonical_language_code(code) or "en"
    except Exception:  # noqa: BLE001
        return code or "en"


class ReaderService:
    def __init__(self, store: ReaderStore | None = None, translator=None):
        self.store = store or get_reader_store()
        # translate(segments, target, *, source_language, user_content) -> list[str]; defaults to the translation chain
        self.translator = translator

    # ------------------------------------------------------------------ open
    async def upload(self, data: bytes, filename: str, owner_key: str) -> ReaderDocument:
        if len(data) > MAX_UPLOAD_BYTES:
            raise ReaderInputError("too_large")
        if not data.startswith(b"%PDF"):
            raise ReaderInputError("not_pdf")
        doc_id = self.store.upload_id(owner_key, data)
        if self.store.exists(doc_id):
            return self.store.get(doc_id, owner_key)
        try:
            text = await asyncio.to_thread(extract_pdf_text, data)
        except PdfUnreadable as error:
            raise ReaderInputError("unreadable") from error
        title = (text.title or "").strip() or os.path.splitext(filename or "")[0].replace("_", " ").strip() or "Untitled document"
        meta = {"title": title[:300], "source": "upload", "authors": [], "is_open_access": False}
        return self.store.save(doc_id, owner_key=owner_key, meta=meta, text=text, pdf=data)

    async def open_paper(self, paper: ReaderPaperRef | None, link: str | None, viewer_key: str) -> ReaderDocument:
        if paper is None and not link:
            raise ReaderInputError("nothing_to_open")
        pdf = await fetch.find_open_pdf(
            pdf_url=paper.pdf_url if paper else None,
            doi=paper.doi if paper else fetch.normalize_doi(link),
            url=paper.url if paper else None,
            link=link,
        )
        meta: dict[str, Any] = {
            "title": (paper.title if paper else None) or "Untitled document",
            "authors": paper.authors if paper else [],
            "year": paper.year if paper else None,
            "venue": paper.venue if paper else None,
            "doi": (paper.doi if paper else None) or fetch.normalize_doi(link),
            "url": (paper.url if paper else None) or link,
            "abstract": paper.abstract if paper else None,
            "is_open_access": bool(pdf) or bool(paper and paper.is_open_access),
            "citation_count": paper.citation_count if paper else 0,
        }
        if pdf:
            doc_id = self.store.public_id(pdf, "")
            if self.store.exists(doc_id):
                return self.store.get(doc_id, viewer_key)
            try:
                text = await asyncio.to_thread(extract_pdf_text, pdf)
            except PdfUnreadable:
                text = None
            if text and any(page.strip() for page in text.pages):
                if meta["title"] == "Untitled document" and text.title:
                    meta["title"] = text.title
                return self.store.save(doc_id, owner_key=None, meta={**meta, "source": "open_access"}, text=text, pdf=pdf)
        abstract = (paper.abstract or "").strip() if paper else ""
        if not abstract:
            raise ReaderInputError("no_full_text")
        key = f"abstract:{(paper.doi or paper.paper_id or paper.title).lower()}" if paper else f"abstract:{link}"
        doc_id = self.store.public_id(None, key)
        if self.store.exists(doc_id):
            return self.store.get(doc_id, viewer_key)
        return self.store.save(doc_id, owner_key=None, meta={**meta, "source": "abstract"}, text=None, pages=[abstract])

    # ------------------------------------------------------------------ read
    def document(self, doc_id: str, viewer_key: str) -> ReaderDocument:
        return self.store.get(doc_id, viewer_key)

    def pages(self, doc_id: str, viewer_key: str, start: int, end: int) -> list[tuple[int, str]]:
        pages = self.store.pages(doc_id, viewer_key)
        start = max(1, start)
        end = min(len(pages), max(start, end))
        return [(number, pages[number - 1]) for number in range(start, end + 1)]

    # ------------------------------------------------------------------ summary
    def cached_summary(self, doc_id: str, viewer_key: str, level: str, language: str) -> ReaderSummary | None:
        self.store.get(doc_id, viewer_key)
        cached = self.store.cache_get(doc_id, f"summary:{level}:{_language(language)}")
        return ReaderSummary(**cached) if cached else None

    def summarize(self, doc_id: str, viewer_key: str, level: str, language: str) -> ReaderSummary:
        language = _language(language)
        document = self.store.get(doc_id, viewer_key)
        pages = self.store.pages(doc_id, viewer_key)
        private = self.store.is_private(doc_id, viewer_key)
        try:
            summary = intelligence.ai_summary(pages, level=level, language=language, private=private, basis=document.source)
        except intelligence.ReaderAIUnavailable:
            summary = intelligence.basic_summary(
                pages,
                level=level,
                language=language,
                basis=document.source,
                translate=lambda texts: self._translate(texts, language, private),  # noqa: B023
            )
        if not summary.basic:
            self.store.cache_put(doc_id, f"summary:{level}:{language}", summary.model_dump())
        return summary

    # ------------------------------------------------------------------ ask
    def ask(self, doc_id: str, viewer_key: str, question: str, language: str) -> ReaderAnswer:
        language = _language(language)
        self.store.get(doc_id, viewer_key)
        pages = self.store.pages(doc_id, viewer_key)
        private = self.store.is_private(doc_id, viewer_key)
        retrieval_query = question
        if language != "en":
            try:  # retrieve with an English version of the question; papers are mostly in English
                retrieval_query = f"{question} {self._translate([question], 'en', True)[0]}"
            except Exception:  # noqa: BLE001
                retrieval_query = question
        return intelligence.ai_answer(pages, question, language=language, private=private, retrieval_query=retrieval_query)

    # ------------------------------------------------------------------ translate
    def cached_translation(self, doc_id: str, viewer_key: str, numbers: list[int], language: str) -> TranslateResponse | None:
        language = _language(language)
        self.store.get(doc_id, viewer_key)
        cached = [self.store.cache_get(doc_id, f"translate:{language}:{number}") for number in numbers]
        if all(cached):
            return TranslateResponse(language=language, pages=cached)  # type: ignore[arg-type]
        return None

    def translate(self, doc_id: str, viewer_key: str, numbers: list[int], language: str) -> TranslateResponse:
        language = _language(language)
        pages = self.store.pages(doc_id, viewer_key)
        private = self.store.is_private(doc_id, viewer_key)
        wanted = sorted({number for number in numbers if 1 <= number <= len(pages)})
        if not wanted:
            raise ReaderInputError("bad_pages")
        translated = intelligence.translate_pages(pages, wanted, language=language, private=private, translate=self.translator)
        for item in translated:
            self.store.cache_put(doc_id, f"translate:{language}:{item.page}", item.model_dump())
        return TranslateResponse(language=language, pages=translated)

    def _translate(self, texts: list[str], language: str, private: bool) -> list[str]:
        if self.translator is not None:
            return self.translator(texts, language, source_language="auto", user_content=private)
        from app.services.search.translation import translate_batch

        return translate_batch(texts, language, source_language="auto", user_content=private)


_service: ReaderService | None = None


def get_reader_service() -> ReaderService:
    global _service
    if _service is None:
        _service = ReaderService()
    return _service


__all__ = ["DocumentNotFound", "ReaderInputError", "ReaderService", "get_reader_service"]
