"""Reader: PDF pages, privacy of uploads, grounded summaries/answers, credits. Fake AI only, no network."""

import asyncio
import json
from types import SimpleNamespace

import pytest

import app.services.ai_router as ai_router
from app.schemas.reader import ReaderPaperRef
from app.services.reader import fetch, intelligence
from app.services.reader.pdf_text import extract_pdf_text, find_captions
from app.services.reader.service import ReaderInputError, ReaderService
from app.services.reader.store import DocumentNotFound, ReaderStore


def make_pdf(pages: list[list[str]]) -> bytes:
    """A small, valid text PDF (one Helvetica text block per page) without extra dependencies."""
    objects: list[bytes] = []
    page_ids = [4 + index * 2 for index in range(len(pages))]
    objects.append(b"<< /Type /Catalog /Pages 2 0 R >>")
    objects.append(b"<< /Type /Pages /Kids [" + b" ".join(f"{pid} 0 R".encode() for pid in page_ids) + f"] /Count {len(pages)} >>".encode())
    objects.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
    for index, lines in enumerate(pages):
        stream = "BT /F1 11 Tf 50 780 Td 14 TL " + " ".join(f"({line.replace('(', '[').replace(')', ']')}) Tj T*" for line in lines) + " ET"
        content_id = page_ids[index] + 1
        objects.append(f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources << /Font << /F1 3 0 R >> >> /Contents {content_id} 0 R >>".encode())
        objects.append(f"<< /Length {len(stream)} >>\nstream\n{stream}\nendstream".encode())
    output = bytearray(b"%PDF-1.4\n")
    offsets = []
    for number, body in enumerate(objects, start=1):
        offsets.append(len(output))
        output += f"{number} 0 obj\n".encode() + body + b"\nendobj\n"
    xref = len(output)
    output += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode()
    output += b"".join(f"{offset:010d} 00000 n \n".encode() for offset in offsets)
    output += f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    return bytes(output)


PAGES = [
    ["Grounded decoding for vision-language models", "Abstract. We propose a training-free decoding method.", "It reduces object hallucination in image captions."],
    ["3 Method", "Our method re-weights tokens using visual evidence.", "Figure 1: Overview of the grounded decoding pipeline."],
    ["5 Results", "On the POPE benchmark F1 rises from 83.9 to 86.9.", "Table 2: Results on POPE and CHAIR benchmarks.", "Limitations: we only test English captions."],
]


@pytest.fixture
def service(tmp_path):
    return ReaderService(ReaderStore(tmp_path / "reader"))


class FakeRouter:
    routes = {"summary": (), "chat": ()}

    def __init__(self, outputs):
        self.outputs = list(outputs)
        self.calls = []

    def complete(self, task, prompt, **kwargs):
        self.calls.append({"task": task, "prompt": json.loads(prompt), **kwargs})
        validator = kwargs.get("validator")
        while self.outputs:
            text = self.outputs.pop(0)
            if validator is None or validator(text):
                return SimpleNamespace(text=text, provider="fake")
        raise ai_router.RouterUnavailable("no valid output")


def install(monkeypatch, outputs):
    router = FakeRouter(outputs)
    monkeypatch.setattr(ai_router, "get_default_router", lambda: router)
    return router


def test_pdf_pages_and_captions():
    text = extract_pdf_text(make_pdf(PAGES))
    assert len(text.pages) == 3 and "83.9" in text.pages[2]
    captions = find_captions(text.pages)
    assert {(item["kind"], item["number"], item["page"]) for item in captions} == {("figure", 1, 2), ("table", 2, 3)}


def test_uploads_are_private_and_deduplicated(service):
    data = make_pdf(PAGES)
    first = asyncio.run(service.upload(data, "grounded.pdf", "user:a"))
    again = asyncio.run(service.upload(data, "grounded.pdf", "user:a"))
    assert first.id == again.id and first.page_count == 3 and first.source == "upload"
    with pytest.raises(DocumentNotFound):
        service.document(first.id, "user:b")
    with pytest.raises(ReaderInputError):
        asyncio.run(service.upload(b"not a pdf", "x.pdf", "user:a"))


def test_open_falls_back_to_abstract_and_is_shared(service, monkeypatch):
    async def no_pdf(**_):
        return None

    monkeypatch.setattr(fetch, "find_open_pdf", no_pdf)
    paper = ReaderPaperRef(title="A paper", abstract="This study shows that grounded decoding reduces errors.", doi="10.1/x")
    document = asyncio.run(service.open_paper(paper, None, "user:a"))
    assert document.source == "abstract" and document.page_count == 1 and not document.has_pdf
    assert service.document(document.id, "user:b").id == document.id  # public metadata is shared
    with pytest.raises(ReaderInputError):
        asyncio.run(service.open_paper(ReaderPaperRef(title="No abstract"), None, "user:a"))


def _summary(numbers="86.9", pages=(3,)):
    return json.dumps({
        "tldr": {"text": "A decoding method reduces hallucination.", "pages": [1]},
        "key_points": [
            {"text": f"F1 rises to {numbers} on POPE.", "pages": list(pages)},
            {"text": "No training is needed.", "pages": [1]},
        ],
        "sections": {"limitations": {"text": "Only English captions are tested.", "pages": [3]}, "data": {"text": "", "pages": []}},
    })


def test_summary_rejects_invented_numbers_and_bad_pages(service, monkeypatch):
    document = asyncio.run(service.upload(make_pdf(PAGES), "g.pdf", "user:a"))
    router = install(monkeypatch, [_summary("99.5"), _summary(pages=(9,)), _summary()])
    summary = service.summarize(document.id, "user:a", "student", "en")
    assert summary.key_points[0].text == "F1 rises to 86.9 on POPE." and summary.key_points[0].pages == [3]
    assert "data" not in summary.sections and not summary.basic
    assert router.calls[0]["user_content"] is True  # an uploaded PDF is private
    assert service.cached_summary(document.id, "user:a", "student", "en") is not None


def test_summary_falls_back_to_basic_when_ai_is_down(service, monkeypatch):
    document = asyncio.run(service.upload(make_pdf(PAGES), "g.pdf", "user:a"))
    install(monkeypatch, [])
    summary = service.summarize(document.id, "user:a", "simple", "en")
    assert summary.basic and summary.tldr.text and summary.tldr.pages


def test_answers_must_quote_the_cited_page(service, monkeypatch):
    document = asyncio.run(service.upload(make_pdf(PAGES), "g.pdf", "user:a"))
    wrong_quote = json.dumps({"answer": "F1 is 86.9 [p.3]", "citations": [{"page": 3, "quote": "F1 jumps to 99"}]})
    good = json.dumps({"answer": "F1 rises to 86.9 [p.3]", "citations": [{"page": 3, "quote": "F1 rises from 83.9 to 86.9"}], "confidence": "high"})
    install(monkeypatch, [wrong_quote, good])
    answer = service.ask(document.id, "user:a", "What is the F1 on POPE?", "en")
    assert answer.citations[0].page == 3 and answer.confidence == "high"


def test_translation_pages_and_cache(tmp_path):
    calls = []

    def fake_translate(segments, target, **kwargs):
        calls.append(kwargs.get("user_content"))
        return [f"[{target}] {segment}" for segment in segments]

    service = ReaderService(ReaderStore(tmp_path / "reader"), translator=fake_translate)
    document = asyncio.run(service.upload(make_pdf(PAGES), "g.pdf", "user:a"))
    result = service.translate(document.id, "user:a", [3, 99], "ur")
    assert [page.page for page in result.pages] == [3] and result.pages[0].paragraphs[0].startswith("[ur]")
    assert calls == [True]  # a private upload only goes to providers allowed to see user content
    assert service.cached_translation(document.id, "user:a", [3], "ur") is not None


def test_select_for_summary_keeps_page_markers():
    long_pages = [("Introduction " + "word " * 3000) for _ in range(30)]
    selected = intelligence.select_for_summary(long_pages, budget=20000)
    assert selected.startswith("[p.1]") and len(selected) <= 21000
