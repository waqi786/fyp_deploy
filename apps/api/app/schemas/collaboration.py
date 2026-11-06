from pydantic import BaseModel, Field


class CommentThread(BaseModel):
    resource_type: str
    resource_id: str
    comments: list[str] = Field(default_factory=list)
    resolved: bool = False
    participants: list[str] = Field(default_factory=list)


class WorkspaceTask(BaseModel):
    title: str
    assignee: str
    status: str = "open"
    priority: str = "medium"
    due_in_days: int | None = None
    linked_resource_type: str | None = None
    linked_resource_id: str | None = None


class CollaborationRequest(BaseModel):
    workspace_id: str
    comments: list[CommentThread] = Field(default_factory=list)
    tasks: list[WorkspaceTask] = Field(default_factory=list)
    mentions: list[str] = Field(default_factory=list)
    review_mode: str = "comment-only"
    shared_folders: list[str] = Field(default_factory=list)
    meeting_notes: list[str] = Field(default_factory=list)
    digest_channels: list[str] = Field(default_factory=lambda: ["slack", "email", "discord"])
    ai_quota_overrides: dict[str, int] = Field(default_factory=dict)
    guest_review_enabled: bool = True
    share_expiry_days: int = 7
    collaborator_roles: dict[str, str] = Field(default_factory=dict)
    live_document_text: str = ""
    concurrent_edits: list[dict[str, str]] = Field(default_factory=list)
    ai_generated_events: list[dict[str, str]] = Field(default_factory=list)
    template_name: str = "default-research-lab"
    export_packet: bool = True


class ShareLinkSummary(BaseModel):
    resource_type: str
    token: str
    permission: str
    expires_in_days: int


class MemberPresence(BaseModel):
    member: str
    status: str
    assigned_tasks: int


class ReviewCheckpoint(BaseModel):
    label: str
    status: str
    owner: str
    checkpoint_id: str | None = None
    storage_uri: str | None = None


class DigestDeliveryReceipt(BaseModel):
    channel: str
    status: str
    target: str
    message: str


class AIContentAuditEntry(BaseModel):
    event_id: str
    actor: str
    action: str
    resource_id: str
    disclosure_required: bool = True
    timestamp: str


class ConcurrentEditState(BaseModel):
    strategy: str
    document_version: str
    merged_text: str
    operations_applied: int
    conflict_count: int


class TaskAssignmentSummary(BaseModel):
    assignee: str
    open_tasks: int
    in_review_tasks: int
    overdue_risk: int


class CollaborationResponse(BaseModel):
    activity_feed: list[str]
    notifications: list[str]
    team_dashboard: dict[str, int]
    supervisor_mode: str
    research_packet_summary: str
    guest_link: str
    workspace_analytics: dict[str, int]
    concurrency_strategy: str
    meeting_note_links: list[str]
    digests: list[str]
    ai_usage_quotas: dict[str, int]
    audit_summary: str
    template_workspace: str
    share_links: list[ShareLinkSummary]
    task_board: dict[str, int]
    member_presence: list[MemberPresence]
    review_checkpoints: list[ReviewCheckpoint]
    task_assignments: list[TaskAssignmentSummary]
    role_summary: dict[str, int]
    collaborator_roles: dict[str, str]
    shared_folder_summary: list[str]
    guest_review_policy: dict[str, str | int | bool]
    review_threads_by_resource: dict[str, int]
    mention_directory: dict[str, str]
    checkpoint_export_status: dict[str, str]
    packet_contents: list[str]
    realtime_channels: list[str] = Field(default_factory=list)
    inline_comment_threads: list[CommentThread] = Field(default_factory=list)
    digest_delivery_receipts: list[DigestDeliveryReceipt] = Field(default_factory=list)
    ai_content_audit_log: list[AIContentAuditEntry] = Field(default_factory=list)
    concurrent_edit_state: ConcurrentEditState | None = None
    research_packet_archive_uri: str | None = None
    research_packet_byte_size: int = 0
    workspace_snapshot_uri: str | None = None
    template_workspace_options: list[str] = Field(default_factory=list)
    rbac_matrix: dict[str, list[str]] = Field(default_factory=dict)
    generated_at: str
