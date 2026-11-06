from pydantic import BaseModel, Field

from app.schemas.paper import PaperRecord


class DeveloperPlatformRequest(BaseModel):
    user_id: str
    workspace_id: str
    api_key_name: str = "default"
    scopes: list[str] = Field(default_factory=lambda: ["search:read", "chat:write"])
    webhook_url: str = "https://example.org/webhook"
    reference_blob: str = "[]"
    reference_format: str = "json"
    prompt_templates: dict[str, str] = Field(default_factory=dict)
    webhook_events: list[str] = Field(default_factory=lambda: ["search.match.created", "review.updated"])
    plugin_filters: list[str] = Field(default_factory=list)


class ApiKeySummary(BaseModel):
    key_prefix: str
    scopes: list[str]
    rotation_hint: str
    expires_at: str
    revocation_endpoint: str
    rate_limit_per_minute: int


class WebhookPreview(BaseModel):
    url: str
    events: list[str]
    delivery_mode: str
    retry_policy: str
    signature_header: str
    secret_rotation: str
    sample_payload: dict[str, str]
    delivery_receipt_id: str


class ImportJobSummary(BaseModel):
    format: str
    imported_count: int
    dropped_count: int
    status: str
    artifact_uri: str
    validation_errors: list[str]


class PluginCapabilitySummary(BaseModel):
    plugin_type: str
    names: list[str]
    capabilities: dict[str, list[str]]


class AdminDashboardSummary(BaseModel):
    system_health: str
    active_workspaces: int
    api_calls_today: int
    estimated_cost_usd: float
    queued_webhooks: int
    plugin_count: int
    import_jobs_today: int
    uptime_status: str
    usage_by_route: dict[str, int]
    cost_breakdown: dict[str, float]
    rate_limit_remaining: int
    queue_depth: int
    last_backup_status: str


class GraphQLQueryRequest(BaseModel):
    query: str
    variables: dict[str, str | int | float | bool] = Field(default_factory=dict)


class GraphQLQueryResponse(BaseModel):
    data: dict
    schema_overview: list[str]


class BrowserExtensionIntakeRequest(BaseModel):
    title: str
    url: str
    selection: str = ""


class BrowserExtensionIntakeResponse(BaseModel):
    status: str
    saved_item_id: str
    preview: str
    route_hint: str | None = None


class DeveloperPlatformResponse(BaseModel):
    rest_endpoints: list[str]
    openapi_url: str
    graphql_endpoint: str
    graphql_schema_overview: list[str]
    issued_api_key: str
    api_key_summary: ApiKeySummary
    api_key_lifecycle: list[str]
    webhook_delivery_preview: str
    webhook_preview: WebhookPreview
    webhook_signing_secret_preview: str
    integrations: dict[str, str]
    integration_sync_jobs: list[dict[str, str]]
    browser_extension_path: str
    extension_manifest: dict[str, object]
    plugin_summary: dict[str, list[str]]
    plugin_capabilities: list[PluginCapabilitySummary]
    prompt_templates: dict[str, str]
    saved_prompt_template_ids: list[str]
    imported_references: list[PaperRecord]
    import_job: ImportJobSummary
    bulk_import_artifact_uri: str
    cli_examples: list[str]
    admin_dashboard: AdminDashboardSummary
    admin_health_checks: list[dict[str, str]]
    developer_audit_events: list[str]
    generated_at: str
