"""Reader: one place to read, summarize, ask, translate and listen to a paper."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator

Level = Literal["expert", "student", "simple"]
DocumentSource = Literal["upload", "open_access", "abstract"]


class ReaderPaperRef(BaseModel):
    """Public metadata of a search result, sent when the user opens it in the Reader."""

    paper_id: str | None = Field(default=None, max_length=300)
    title: str = Field(min_length=1, max_length=600)
    abstract: str | None = Field(default=None, max_length=12000)
    authors: list[str] = Field(default_factory=list, max_length=60)
    year: int | None = None
    venue: str | None = Field(default=None, max_length=300)
    doi: str | None = Field(default=None, max_length=300)
    url: str | None = Field(default=None, max_length=2000)
    pdf_url: str | None = Field(default=None, max_length=2000)
    is_open_access: bool = False
    citation_count: int = 0

    @field_validator("authors")
    @classmethod
    def _short_names(cls, values: list[str]) -> list[str]:
        return [value.strip()[:120] for value in values if value and value.strip()]


class ReaderOpenRequest(BaseModel):
    paper: ReaderPaperRef | None = None
    link: str | None = Field(default=None, max_length=2000, description="A DOI, arXiv id or https link to a PDF")


class ReaderCaption(BaseModel):
    kind: Literal["figure", "table"]
    number: int
    page: int
    caption: str


class ReaderDocument(BaseModel):
    id: str
    title: str
    authors: list[str] = Field(default_factory=list)
    year: int | None = None
    venue: str | None = None
    doi: str | None = None
    url: str | None = None
    abstract: str | None = None
    source: DocumentSource
    has_pdf: bool
    page_count: int
    word_count: int
    reading_minutes: int
    scanned_pages: list[int] = Field(default_factory=list)
    captions: list[ReaderCaption] = Field(default_factory=list)
    is_open_access: bool = False
    citation_count: int = 0


class ReaderPage(BaseModel):
    page: int
    text: str


class ReaderPagesResponse(BaseModel):
    pages: list[ReaderPage]


class SummaryRequest(BaseModel):
    level: Level = "student"
    language: str = Field(default="en", max_length=20)


class SummaryPoint(BaseModel):
    text: str
    pages: list[int] = Field(default_factory=list)


class ReaderSummary(BaseModel):
    tldr: SummaryPoint
    key_points: list[SummaryPoint]
    sections: dict[str, SummaryPoint]
    level: Level
    language: str
    basis: DocumentSource
    basic: bool = False  # True when AI was unavailable and a simple extractive summary was built
    credits_used: int = 0


class AskRequest(BaseModel):
    question: str = Field(min_length=2, max_length=1200)
    language: str = Field(default="en", max_length=20)


class ReaderCitation(BaseModel):
    page: int
    quote: str


class ReaderAnswer(BaseModel):
    answer: str
    citations: list[ReaderCitation] = Field(default_factory=list)
    confidence: Literal["high", "medium", "low"] = "medium"
    not_found: bool = False
    language: str
    credits_used: int = 0


class TranslateRequest(BaseModel):
    pages: list[int] = Field(min_length=1, max_length=5)
    language: str = Field(max_length=20)


class TranslatedPage(BaseModel):
    page: int
    paragraphs: list[str]
    original: list[str]


class TranslateResponse(BaseModel):
    language: str
    pages: list[TranslatedPage]
    credits_used: int = 0
