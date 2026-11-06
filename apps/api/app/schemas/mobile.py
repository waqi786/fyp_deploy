from pydantic import BaseModel, Field


class MobileExperienceRequest(BaseModel):
    workspace_id: str
    saved_papers: list[str] = Field(default_factory=list)
    saved_summaries: list[str] = Field(default_factory=list)
    offline_actions: list[str] = Field(default_factory=list)
    saved_searches: list[str] = Field(default_factory=list)
    low_data_mode: bool = False
    voice_enabled: bool = True
    device_type: str = "phone"
    push_enabled: bool = True
    last_device: str | None = None
    pdf_id: str | None = None
    triage_mode: str = "swipe"


class OfflineBundle(BaseModel):
    name: str
    items: int
    priority: str


class SyncManifest(BaseModel):
    queued_actions: int
    retry_policy: str
    next_sync_mode: str


class CachePolicy(BaseModel):
    mode: str
    max_items: int
    evicts_after_hours: int


class ContinuityPayload(BaseModel):
    handoff_token: str
    source_device: str | None = None
    target_devices: list[str] = Field(default_factory=list)


class MobileExperienceResponse(BaseModel):
    installable: bool
    pwa_install_prompt: dict[str, str | bool]
    offline_cache_plan: list[str]
    offline_bundles: list[OfflineBundle]
    mobile_voice_mode: str
    push_notifications: list[str]
    push_categories: list[str]
    low_data_mode: str
    swipe_triage_queue: list[str]
    swipe_triage_actions: list[dict[str, str]]
    background_sync_status: str
    sync_manifest: SyncManifest
    cache_policy: CachePolicy
    pdf_mobile_features: list[str]
    mobile_pdf_viewer_state: dict[str, str | bool]
    continuity_status: str
    continuity_payload: ContinuityPayload
    device_layout: str
    offline_readiness_score: float
    qr_share_payloads: dict[str, str]
    qr_share_metadata: dict[str, dict[str, str]]
    cross_platform_targets: list[str]
    generated_at: str
