"""Public models for researcher and institution search and profile pages."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class TraceableAIOutput(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    confidence_score: float = 0.0
    source_span: list[str] = Field(default_factory=list)
    model_used: str = ""
    generated_at: str = ""


class ApiKeyEntity(BaseModel):
    id: str
    user_id: str
    workspace_id: str
    name: str
    key_prefix: str
    key_hash: str
    scopes: list[str] = Field(default_factory=list)
    last_used_at: str | None = None
    created_at: str




class EntitySummary(BaseModel):
    id: str
    kind: Literal["researcher", "institution"]
    name: str
    subtitle: str | None = None
    works_count: int = 0
    cited_by_count: int = 0


class EntityMatches(BaseModel):
    researchers: list[EntitySummary] = Field(default_factory=list)
    institutions: list[EntitySummary] = Field(default_factory=list)


class WorkItem(BaseModel):
    title: str
    translated_title: str | None = None
    year: int | None = None
    venue: str | None = None
    citation_count: int = 0
    doi: str | None = None
    url: str | None = None
    is_open_access: bool = False


class YearCount(BaseModel):
    year: int
    works: int = 0
    citations: int = 0


class Topic(BaseModel):
    name: str
    translated_name: str | None = None
    count: int = 0


class PersonLink(BaseModel):
    id: str | None = None
    name: str
    subtitle: str | None = None
    count: int = 0


class ResearcherProfile(BaseModel):
    id: str
    name: str
    affiliations: list[str] = Field(default_factory=list)
    orcid: str | None = None
    works_count: int = 0
    cited_by_count: int = 0
    h_index: int | None = None
    topics: list[Topic] = Field(default_factory=list)
    timeline: list[YearCount] = Field(default_factory=list)
    top_works: list[WorkItem] = Field(default_factory=list)
    recent_works: list[WorkItem] = Field(default_factory=list)
    collaborators: list[PersonLink] = Field(default_factory=list)


class InstitutionProfile(BaseModel):
    id: str
    name: str
    country: str | None = None
    type: str | None = None
    homepage: str | None = None
    works_count: int = 0
    cited_by_count: int = 0
    topics: list[Topic] = Field(default_factory=list)
    timeline: list[YearCount] = Field(default_factory=list)
    top_researchers: list[PersonLink] = Field(default_factory=list)
    top_works: list[WorkItem] = Field(default_factory=list)
