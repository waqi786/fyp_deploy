"""Page-by-page text from a PDF, with permissive libraries first.

Order (Master Prompt Part 12, license-safe pipeline):
  1. pypdfium2  (Apache-2.0 / BSD) — fast, accurate reading order for most papers;
  2. pdfplumber (MIT)              — fallback for PDFs pdfium cannot open;
  3. PyMuPDF    (AGPL)             — only if already installed AND READER_ALLOW_PYMUPDF=1 (documented decision).
Scanned pages (no text layer) are reported, so the UI can say "this page is an image" instead of guessing.
"""

from __future__ import annotations

import io
import logging
import os
import re
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

MAX_PAGES = int(os.getenv("READER_MAX_PAGES", "400"))
CAPTION = re.compile(r"(?im)^\s*((?:fig(?:ure)?\.?|table)\s*(\d{1,3})[.:\-–]?\s+([^\n]{8,800}))$")


@dataclass
class PdfText:
    pages: list[str]
    engine: str
    scanned_pages: list[int] = field(default_factory=list)
    title: str | None = None


class PdfUnreadable(ValueError):
    pass


HEADING = re.compile(r"^((\d+(\.\d+)*\.?)|[IVX]+\.|abstract|references|acknowledg(e)?ments?)\s*[A-Z]?", re.IGNORECASE)
CAPTION_START = re.compile(r"^(fig(ure)?\.?|table)\s*\d", re.IGNORECASE)


def _clean(text: str) -> str:
    """Rebuild paragraphs from PDF lines: join wrapped lines, keep headings and captions on their own."""
    text = text.replace("\r\n", "\n").replace("\r", "\n").replace("\x00", "").replace("\u00a0", " ")
    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in text.split("\n")]
    lengths = sorted(len(line) for line in lines if line)
    typical = lengths[int(len(lengths) * 0.75)] if lengths else 0
    paragraphs: list[str] = []
    buffer: list[str] = []

    def flush() -> None:
        if buffer:
            joined = ""
            for part in buffer:
                if joined.endswith("-") and part[:1].islower():
                    joined = joined[:-1] + part  # word split across lines
                else:
                    joined = f"{joined} {part}".strip()
            paragraphs.append(joined)
            buffer.clear()

    for line in lines:
        if not line:
            flush()
            continue
        heading = len(line) < 80 and bool(HEADING.match(line)) and not line.endswith((",", ";"))
        caption = bool(CAPTION_START.match(line))
        if heading or caption:
            flush()
        in_caption = caption or (bool(buffer) and bool(CAPTION_START.match(buffer[0])))
        buffer.append(line)
        short = typical > 0 and len(line) < typical * 0.72
        ends_sentence = line.endswith((".", ":", "?", "!", "。", "؟", "۔"))
        if heading or (ends_sentence and (short or in_caption)):
            flush()
    flush()
    return "\n\n".join(paragraphs).strip()


def _with_pdfium(data: bytes) -> PdfText | None:
    try:
        import pypdfium2 as pdfium  # type: ignore
    except Exception:  # noqa: BLE001
        return None
    try:
        document = pdfium.PdfDocument(data)
    except Exception:  # noqa: BLE001
        return None
    try:
        pages: list[str] = []
        for index in range(min(len(document), MAX_PAGES)):
            page = document[index]
            text_page = page.get_textpage()
            pages.append(_clean(text_page.get_text_range()))
            text_page.close()
            page.close()
        title = None
        try:
            title = (document.get_metadata_dict() or {}).get("Title") or None
        except Exception:  # noqa: BLE001
            title = None
        return PdfText(pages=pages, engine="pdfium", title=title)
    finally:
        document.close()


def _with_pdfplumber(data: bytes) -> PdfText | None:
    try:
        import pdfplumber  # type: ignore
    except Exception:  # noqa: BLE001
        return None
    try:
        with pdfplumber.open(io.BytesIO(data)) as document:
            pages = [_clean(page.extract_text() or "") for page in document.pages[:MAX_PAGES]]
            title = (document.metadata or {}).get("Title") or None
        return PdfText(pages=pages, engine="pdfplumber", title=title)
    except Exception:  # noqa: BLE001
        return None


def _with_pymupdf(data: bytes) -> PdfText | None:
    if os.getenv("READER_ALLOW_PYMUPDF", "1") != "1":
        return None
    try:
        import fitz  # type: ignore
    except Exception:  # noqa: BLE001
        return None
    try:
        document = fitz.open(stream=data, filetype="pdf")
        pages = [_clean(page.get_text("text")) for page in list(document)[:MAX_PAGES]]
        return PdfText(pages=pages, engine="pymupdf", title=(document.metadata or {}).get("title") or None)
    except Exception:  # noqa: BLE001
        return None


def extract_pdf_text(data: bytes) -> PdfText:
    if not data.startswith(b"%PDF"):
        raise PdfUnreadable("not a PDF")
    for engine in (_with_pdfium, _with_pdfplumber, _with_pymupdf):
        result = engine(data)
        if result and result.pages:
            result.scanned_pages = [index + 1 for index, page in enumerate(result.pages) if len(page) < 40]
            return result
    raise PdfUnreadable("could not read this PDF")


def find_captions(pages: list[str]) -> list[dict[str, object]]:
    """Figure and table captions with their page numbers (first occurrence of each label)."""
    seen: set[tuple[str, str]] = set()
    captions: list[dict[str, object]] = []
    for page_number, text in enumerate(pages, start=1):
        for match in CAPTION.finditer(text):
            label_word = match.group(1).split()[0].lower()
            kind = "table" if label_word.startswith("table") else "figure"
            number = match.group(2)
            if (kind, number) in seen:
                continue
            seen.add((kind, number))
            caption = re.sub(r"\s+", " ", match.group(3)).strip()
            caption = re.split(r"(?<=\.)\s+(?=[A-Z])", caption, maxsplit=1)[0]  # the caption's first sentence
            captions.append({"kind": kind, "number": int(number), "page": page_number, "caption": caption[:320]})
    return sorted(captions, key=lambda item: (item["kind"] != "figure", item["number"]))
