from pydantic import BaseModel, Field


class PersonalizationRequest(BaseModel):
    user_type: str = "researcher"
    reading_history: list[str] = Field(default_factory=list)
    verbosity: str = "balanced"
    offline_items: list[str] = Field(default_factory=list)
    low_bandwidth: bool = False
    ui_language: str = "en"
    rtl_enabled: bool = False
    theme: str = "dark"
    font_size: str = "medium"
    dyslexia_friendly: bool = False
    tts_enabled: bool = True
    dashboard_widgets: list[str] = Field(default_factory=list)
    digest_frequency: str = "weekly"
    device_ids: list[str] = Field(default_factory=list)
    glossary_seed_terms: list[str] = Field(default_factory=list)
    data_action: str | None = None


class PersonalizationResponse(BaseModel):
    recommended_topics: list[str]
    home_feed: list[str]
    dashboard_widgets: list[str]
    glossary_terms: list[str]
    weekly_digest: str
    scheduled_digest: dict[str, str]
    onboarding_path: list[str]
    accessibility_profile: dict[str, str]
    urdu_ui: dict[str, str | bool]
    font_controls: dict[str, str | bool]
    tts_controls: dict[str, str | bool]
    keyboard_navigation_map: list[str]
    screen_reader_landmarks: list[str]
    wcag_aa_checklist: dict[str, bool]
    contextual_help_tooltips: dict[str, str]
    color_blind_safe_palette: dict[str, str]
    offline_reading_list: list[dict[str, str]]
    pwa_cache_manifest: dict[str, list[str] | str | int]
    low_bandwidth_mode: dict[str, str | bool]
    multi_device_sync: dict[str, str | int | list[str]]
    customizable_dashboard: dict[str, list[str] | str]
    similar_to_read_feed: list[str]
    ai_preferences: dict[str, str]
    personal_glossary: dict[str, str]
    sync_status: str
    gdpr_actions: list[str]
    data_export_uri: str | None = None
    data_delete_receipt: str | None = None
    profile_snapshot_uri: str | None = None
