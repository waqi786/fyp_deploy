"""Public request/response models for "Research with Resora", "Ask about these results" and identifier lookup."""

from typing import Literal

from pydantic import BaseModel, Field, field_validator

from app.services.language.config import canonical_language_code

EvidenceLevel = Literal["strong", "moderate", "limited", "hypothesis"]


class ResearchRequest(BaseModel):
    query: str = Field(min_length=2, max_length=500)
    language: str = "en"
    year_from: int | None = Field(default=None, ge=1900)
    year_to: int | None = Field(default=None, le=2100)
    open_access_only: bool = False
    peer_reviewed_only: bool = False
    preprint_only: bool = False
    include_retracted: bool = False
    study_type: str | None = None
    paper_language: str | None = None
    min_citations: int = Field(default=0, ge=0)
    author: str | None = None
    venue: str | None = None

    @field_validator("language")
    @classmethod
    def _language(cls, value: str) -> str:
        return canonical_language_code(value or "en")


class AskPaper(BaseModel):
    paper_id: str = Field(min_length=1, max_length=300)
    title: str = Field(min_length=1, max_length=1000)
    abstract: str | None = Field(default=None, max_length=6000)
    year: int | None = None
    venue: str | None = Field(default=None, max_length=300)


class AskRequest(BaseModel):
    question: str = Field(min_length=2, max_length=500)
    language: str = "en"
    papers: list[AskPaper] = Field(min_length=1, max_length=15)

    @field_validator("language")
    @classmethod
    def _language(cls, value: str) -> str:
        return canonical_language_code(value or "en")


class ResearchApproach(BaseModel):
    label: str
    paper_ids: list[str] = Field(default_factory=list)


class ResearchFinding(BaseModel):
    text: str
    paper_ids: list[str] = Field(default_factory=list)


class ResearchGap(ResearchFinding):
    evidence_level: EvidenceLevel = "limited"


class ResearchAnswer(BaseModel):
    """`answer` contains citation markers like [1] or [2, 3]; marker n refers to evidence_ids[n - 1]."""

    answer: str
    evidence_ids: list[str] = Field(default_factory=list)
    approaches: list[ResearchApproach] = Field(default_factory=list)
    emerging: list[ResearchFinding] = Field(default_factory=list)
    conflicting: list[ResearchFinding] = Field(default_factory=list)
    gaps: list[ResearchGap] = Field(default_factory=list)
    insufficient_evidence: bool = False
    language: str = "en"
    credits_used: int = 0


class CreditEstimate(BaseModel):
    research_credits: int
    ask_credits: int
