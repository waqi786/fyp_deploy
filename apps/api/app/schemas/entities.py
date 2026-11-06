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




class SummaryEntity(TraceableAIOutput):
    id: str
    paper_id: str | None = None
    tier: str
    content: dict = Field(default_factory=dict)


class MessageEntity(TraceableAIOutput):
    id: str
    workspace_id: str | None = None
    role: str
    content: str
    citations: list[dict] = Field(default_factory=list)
    created_at: str


class CitationEntity(TraceableAIOutput):
    id: str
    source_paper_id: str | None = None
    target_paper_id: str | None = None
    sentiment: str = "mention"
    context: str | None = None
    created_at: str | None = None


class LiteratureReviewEntity(TraceableAIOutput):
    id: str
    workspace_id: str | None = None
    title: str
    sections: list[dict] = Field(default_factory=list)


class ComparisonRowEntity(TraceableAIOutput):
    id: str
    comparison_id: str | None = None
    paper_id: str | None = None
    strengths: list[str] = Field(default_factory=list)
    weaknesses: list[str] = Field(default_factory=list)
    extracted_columns: dict = Field(default_factory=dict)
    similarity_score: float = 0.0


class GapReportEntity(TraceableAIOutput):
    id: str
    workspace_id: str | None = None
    title: str
    findings: list[dict] = Field(default_factory=list)


class NoteEntity(BaseModel):
    id: str
    user_id: str | None = None
    workspace_id: str | None = None
    paper_id: str | None = None
    title: str
    content: str
    created_at: str
    updated_at: str


class CollaboratorEntity(BaseModel):
    id: str
    workspace_id: str | None = None
    user_id: str | None = None
    invited_email: str | None = None
    role: str
    status: str = "active"
    invited_at: str
    accepted_at: str | None = None


class ShareLinkEntity(BaseModel):
    id: str
    workspace_id: str | None = None
    resource_type: str
    resource_id: str
    permission: str = "view"
    token: str
    expires_at: str | None = None
    created_by: str | None = None
    created_at: str


class PlagiarismCheckResultEntity(TraceableAIOutput):
    id: str
    literature_review_id: str | None = None
    score: float = 0.0
    flagged_spans: list[dict] = Field(default_factory=list)
    created_at: str


class ExportJobEntity(BaseModel):
    id: str
    workspace_id: str | None = None
    export_type: str
    status: str = "pending"
    payload: dict = Field(default_factory=dict)
    output_uri: str | None = None
    created_at: str


class RefreshTokenEntity(BaseModel):
    id: str
    user_id: str | None = None
    workspace_id: str | None = None
    token_hash: str
    expires_at: str
    revoked_at: str | None = None
    created_at: str


class PrivateNoteEntity(BaseModel):
    id: str
    user_id: str | None = None
    workspace_id: str | None = None
    title: str
    encrypted_content: str
    encryption_hint: str | None = None
    created_at: str
    updated_at: str


class BackupRunEntity(BaseModel):
    id: str
    scope: str
    status: str
    storage_uri: str
    verified_at: str | None = None
    created_at: str


class WebhookSubscriptionEntity(BaseModel):
    id: str
    workspace_id: str | None = None
    target_url: str
    event_types: list[str] = Field(default_factory=list)
    secret_hash: str | None = None
    active: bool = True
    created_at: str


class PromptTemplateEntity(BaseModel):
    id: str
    user_id: str | None = None
    workspace_id: str | None = None
    name: str
    body: str
    tags: list[str] = Field(default_factory=list)
    created_at: str
    updated_at: str


class ImportJobEntity(BaseModel):
    id: str
    workspace_id: str | None = None
    format: str
    item_count: int = 0
    status: str = "pending"
    created_at: str


class PluginRegistrationEntity(BaseModel):
    id: str
    name: str
    plugin_type: str
    capabilities: list[str] = Field(default_factory=list)
    status: str = "active"
    created_at: str


class ReviewSubscriptionEntity(BaseModel):
    id: str
    workspace_id: str | None = None
    query: str
    last_digest_at: str | None = None
    active: bool = True
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
