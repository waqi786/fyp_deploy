"""Write tab models (reviews, drafts, screening, claim checks). The legacy writing.py / draft.py models are untouched."""

from typing import Any, Literal

from pydantic import BaseModel, Field

ReviewStyle = Literal["thematic", "methodological", "chronological", "narrative"]
DraftType = Literal["introduction", "related_work", "abstract", "research_questions", "proposal", "conclusion"]
CitationStyle = Literal["apa", "mla", "chicago", "harvard", "ieee", "vancouver"]
Decision = Literal["include", "exclude", "maybe"]


class WriteSection(BaseModel):
    id: str = Field(min_length=1, max_length=60)
    heading: str = Field(default="", max_length=300)
    purpose: str = Field(default="section", max_length=60)
    papers: list[int] = Field(default_factory=list, max_length=500)
    text: str = Field(default="", max_length=60000)
    status: Literal["empty", "generated", "edited"] = "empty"
    unsupported: list[str] = Field(default_factory=list)


class WriteSource(BaseModel):
    item_id: str | None = None
    title: str
    authors: list[str] = Field(default_factory=list)
    year: int | None = None
    venue: str | None = None
    doi: str | None = None
    url: str | None = None
    arxiv_id: str | None = None
    abstract: str | None = None


class WriteDocumentCreate(BaseModel):
    kind: Literal["review", "draft"]
    title: str = Field(min_length=1, max_length=300)
    style: ReviewStyle | DraftType = "thematic"
    language: str = Field(default="en", max_length=16)
    citation_style: CitationStyle = "apa"
    project_id: str | None = None
    item_ids: list[str] = Field(default_factory=list, max_length=500)


class WriteDocumentUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=300)
    language: str | None = Field(default=None, max_length=16)
    citation_style: CitationStyle | None = None
    sections: list[WriteSection] | None = Field(default=None, max_length=60)


class WriteDocument(BaseModel):
    id: str
    kind: Literal["review", "draft"]
    title: str
    style: str
    language: str
    citation_style: CitationStyle
    project_id: str | None = None
    sources: list[WriteSource | None]
    sections: list[WriteSection]
    created_at: str
    updated_at: str


class WriteDocumentSummary(BaseModel):
    id: str
    kind: Literal["review", "draft"]
    title: str
    style: str
    language: str
    project_id: str | None = None
    updated_at: str
    summary: dict[str, int]


class WriteSourcesAdd(BaseModel):
    item_ids: list[str] = Field(min_length=1, max_length=500)


class WriteTheme(BaseModel):
    label: str = Field(min_length=1, max_length=200)
    papers: list[int] = Field(default_factory=list, max_length=500)


class WriteOutlineRequest(BaseModel):
    style: ReviewStyle
    themes: list[WriteTheme] | None = Field(default=None, max_length=20)


class WriteSectionRequest(BaseModel):
    instruction: str = Field(default="", max_length=600)


class WriteExportRequest(BaseModel):
    format: Literal["docx", "markdown", "latex", "html"]
    rtl: bool = False
    references_label: str = Field(default="References", max_length=80)


class ScreeningCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    project_id: str | None = None
    item_ids: list[str] = Field(default_factory=list, max_length=2000)
    criteria: str = Field(default="", max_length=4000)


class ScreeningUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    criteria: str | None = Field(default=None, max_length=4000)


class ScreeningImport(BaseModel):
    item_ids: list[str] = Field(default_factory=list, max_length=2000)
    content: str | None = Field(default=None, max_length=2_000_000)
    filename: str | None = Field(default=None, max_length=200)


class ScreeningDecision(BaseModel):
    ta_decision: Decision | None = None
    ta_reason: str | None = Field(default=None, max_length=300)
    ft_decision: Decision | None = None
    ft_reason: str | None = Field(default=None, max_length=300)
    note: str | None = Field(default=None, max_length=2000)


class ScreeningToLibrary(BaseModel):
    project_id: str | None = None


class ClaimCheckRequest(BaseModel):
    text: str = Field(min_length=5, max_length=20000)
    item_ids: list[str] = Field(default_factory=list, max_length=500)
    project_id: str | None = None
    document_id: str | None = None
    language: str = Field(default="en", max_length=16)


class ClaimEvidence(BaseModel):
    n: int
    quote: str


class ClaimResult(BaseModel):
    claim: str
    verdict: Literal["supported", "conflicting", "mixed", "not_found"]
    strength: Literal["strong", "moderate", "limited"] | None = None
    evidence: list[ClaimEvidence] = Field(default_factory=list)
    safer: str | None = None


class ClaimCheckResponse(BaseModel):
    mode: Literal["ai", "keywords"]
    claims: list[ClaimResult]
    sources: list[dict[str, Any]]
    credits_used: int = 0
