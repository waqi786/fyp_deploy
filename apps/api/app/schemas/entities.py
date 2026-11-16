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


# --- Data-model entities (restored; used by infra/db/schema.sql tests) ---


class WorkspaceEntity(BaseModel):
    id: str
    name: str
    owner_id: str
    created_at: str
    updated_at: str


class ProjectEntity(BaseModel):
    id: str
    workspace_id: str
    name: str
    description: str | None = None
    created_at: str
    updated_at: str


class AuthorEntity(BaseModel):
    id: str
    paper_id: str
    display_name: str
    affiliation: str | None = None
    orcid: str | None = None
    created_at: str


class ConceptEntity(BaseModel):
    id: str
    name: str
    description: str | None = None
    created_at: str


class EmbeddingEntity(BaseModel):
    id: str
    paper_id: str
    chunk_id: str
    chunk_text: str
    vector_model: str
    metadata: dict = Field(default_factory=dict)
    created_at: str


class SummaryEntity(TraceableAIOutput):
    id: str
    paper_id: str
    tier: str
    content: dict = Field(default_factory=dict)


class ComparisonEntity(TraceableAIOutput):
    id: str
    workspace_id: str
    focus: str
    narrative_summary: str | None = None


class ComparisonRowEntity(TraceableAIOutput):
    id: str
    comparison_id: str
    paper_id: str
    strengths: list[str] = Field(default_factory=list)
    weaknesses: list[str] = Field(default_factory=list)
    extracted_columns: dict[str, str] = Field(default_factory=dict)
    similarity_score: float = 0.0


class MessageEntity(TraceableAIOutput):
    id: str
    workspace_id: str
    role: str
    content: str
    citations: list[str] = Field(default_factory=list)
    created_at: str


class GapReportEntity(TraceableAIOutput):
    id: str
    workspace_id: str
    title: str
    findings: list[str] = Field(default_factory=list)


class LiteratureReviewEntity(TraceableAIOutput):
    id: str
    workspace_id: str
    title: str
    sections: list[dict] = Field(default_factory=list)


class CitationEntity(TraceableAIOutput):
    id: str
    source_paper_id: str
    target_paper_id: str
    sentiment: str
    context: str | None = None


class AnnotationEntity(BaseModel):
    id: str
    user_id: str
    paper_id: str
    quote: str
    note: str | None = None
    highlight_span: list[str] = Field(default_factory=list)
    color: str = "yellow"
    created_at: str


class NoteEntity(BaseModel):
    id: str
    user_id: str
    workspace_id: str
    paper_id: str | None = None
    title: str
    content: str
    created_at: str
    updated_at: str


class FolderEntity(BaseModel):
    id: str
    user_id: str
    name: str
    created_at: str


class TagEntity(BaseModel):
    id: str
    user_id: str
    name: str
    created_at: str


class CollaboratorEntity(BaseModel):
    id: str
    workspace_id: str
    user_id: str | None = None
    invited_email: str | None = None
    role: str
    status: str
    invited_at: str
    accepted_at: str | None = None


class ShareLinkEntity(BaseModel):
    id: str
    workspace_id: str
    resource_type: str
    resource_id: str
    permission: str
    token: str
    expires_at: str | None = None
    created_by: str | None = None
    created_at: str


class AuditLogEntity(BaseModel):
    id: str
    workspace_id: str
    actor_user_id: str | None = None
    action: str
    target_type: str
    target_id: str
    metadata: dict = Field(default_factory=dict)
    created_at: str


class NotificationEntity(BaseModel):
    id: str
    user_id: str
    title: str
    body: str
    read_at: str | None = None
    created_at: str


class PlagiarismCheckResultEntity(TraceableAIOutput):
    id: str
    literature_review_id: str
    score: float = 0.0
    flagged_spans: list[str] = Field(default_factory=list)
    created_at: str


class ExportJobEntity(BaseModel):
    id: str
    workspace_id: str
    export_type: str
    status: str
    payload: dict = Field(default_factory=dict)
    output_uri: str | None = None
    created_at: str


class RefreshTokenEntity(BaseModel):
    id: str
    user_id: str
    workspace_id: str
    token_hash: str
    expires_at: str
    created_at: str


class PrivateNoteEntity(BaseModel):
    id: str
    user_id: str
    workspace_id: str
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
    workspace_id: str
    target_url: str
    event_types: list[str] = Field(default_factory=list)
    active: bool = True
    created_at: str


class PromptTemplateEntity(BaseModel):
    id: str
    user_id: str
    workspace_id: str
    name: str
    body: str
    tags: list[str] = Field(default_factory=list)
    created_at: str
    updated_at: str


class ImportJobEntity(BaseModel):
    id: str
    workspace_id: str
    format: str
    item_count: int
    status: str
    created_at: str


class PluginRegistrationEntity(BaseModel):
    id: str
    name: str
    plugin_type: str
    capabilities: list[str] = Field(default_factory=list)
    status: str
    created_at: str


class ReviewSubscriptionEntity(BaseModel):
    id: str
    workspace_id: str
    query: str
    last_digest_at: str | None = None
    active: bool = True
    created_at: str
