from pydantic import BaseModel, Field


class SecurityComplianceRequest(BaseModel):
    workspace_id: str
    user_id: str
    note_title: str | None = None
    private_note: str | None = None
    encryption_secret: str | None = None
    pdf_object_key: str = "papers/sample.pdf"
    source_text: str = ""
    watermark_enabled: bool = True
    refresh_token_ttl_minutes: int = 60
    action: str = "view"
    request_origin: str = "web"
    share_link_requested: bool = False
    auth_provider: str = "email_password"
    oauth_provider: str | None = "google"
    data_region: str = "institution-selected"


class AuditEntry(BaseModel):
    event: str
    actor: str
    severity: str
    trace_id: str


class SignedUrlMetadata(BaseModel):
    object_key: str
    expires_in_seconds: int
    delivery_scope: str


class NoteProtectionStatus(BaseModel):
    encrypted: bool
    preview_available: bool
    storage_mode: str


class AbuseProtectionStatus(BaseModel):
    rate_window_seconds: int
    remaining: int
    limited: bool
    origin: str
    recommended_action: str


class SecurityComplianceResponse(BaseModel):
    auth_methods: list[str]
    oauth_status: dict[str, str | bool]
    session_cookie_policy: dict[str, str | bool | int]
    workspace_rbac: dict[str, list[str]]
    refresh_token: str
    refresh_token_expires_in_minutes: int
    refresh_token_rotation: dict[str, str | int]
    encrypted_private_note: str | None = None
    decrypted_private_note_preview: str | None = None
    note_protection: NoteProtectionStatus
    rate_limit_status: dict[str, int | bool]
    abuse_protection: AbuseProtectionStatus
    gdpr_actions: list[str]
    audit_log_summary: str
    audit_entries: list[AuditEntry]
    watermark_status: str
    signed_pdf_url: str
    signed_url_metadata: SignedUrlMetadata
    prompt_injection_findings: list[str]
    prompt_sanitization_summary: str
    vulnerability_scans: list[str]
    vulnerability_scan_artifacts: dict[str, str]
    backup_status: str
    backup_manifest: dict[str, str | int]
    backup_restore_receipt: str
    error_monitoring: str
    incident_monitoring: dict[str, str | list[str]]
    data_residency_note: str
    data_residency_policy: dict[str, str | bool]
    privacy_posture: str
    compliance_flags: dict[str, bool]
    generated_at: str
