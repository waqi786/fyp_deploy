from pydantic import BaseModel, Field


class WorkspaceSummary(BaseModel):
    workspace_id: str
    name: str
    member_count: int = 1
    project_count: int = 0
    roles: list[str] = Field(default_factory=lambda: ["owner"])
    default_review_mode: str = "comment-only"
    template_origin: str = "blank"
    alerts_enabled: bool = True


class WorkspaceMember(BaseModel):
    user_id: str
    email: str
    role: str


class WorkspaceCreateRequest(BaseModel):
    name: str
    owner_email: str
    template_origin: str = "default-research-lab"
    review_mode: str = "comment-only"
    member_emails: list[str] = Field(default_factory=list)
    notification_channels: list[str] = Field(default_factory=lambda: ["email", "slack"])
    shared_folders: list[str] = Field(default_factory=lambda: ["Core Papers", "Drafts", "Supervisor Notes"])


class WorkspaceDetail(BaseModel):
    workspace_id: str
    name: str
    members: list[WorkspaceMember]
    projects: list[str] = Field(default_factory=list)
    permissions: list[str] = Field(default_factory=list)
    share_capabilities: list[str] = Field(default_factory=list)
    collaboration_modes: list[str] = Field(default_factory=list)
    activity_summary: dict[str, int] = Field(default_factory=dict)
    role_matrix: dict[str, list[str]] = Field(default_factory=dict)
    guest_policy: dict[str, str | int | bool] = Field(default_factory=dict)
    ai_usage_quota_by_role: dict[str, int] = Field(default_factory=dict)
    notification_channels: list[str] = Field(default_factory=list)
    shared_folders: list[str] = Field(default_factory=list)
    research_packet_exports: list[str] = Field(default_factory=list)
    template_origin: str = "blank"
    default_review_mode: str = "comment-only"
    dashboards: list[str] = Field(default_factory=list)
    versioning_enabled: bool = True
    audit_enabled: bool = True
