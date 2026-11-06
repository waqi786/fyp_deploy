from collections import Counter
from datetime import UTC, datetime
import os
from pathlib import Path
from uuid import uuid4

from app.schemas.personalization import PersonalizationRequest, PersonalizationResponse


class PersonalizationService:
    def __init__(self) -> None:
        self.store_dir = Path(os.getenv("RESORA_PROFILE_STORE_DIR", "storage/profiles"))

    def build(self, payload: PersonalizationRequest) -> PersonalizationResponse:
        tokens = Counter(word.lower() for item in payload.reading_history for word in item.split())
        recommended = [token.title() for token, _ in tokens.most_common(5)] or ["Retrieval", "Benchmark", "Multimodal"]
        widgets = payload.dashboard_widgets or ["Reading Queue", "Trend Radar", "Saved Searches"]
        if payload.low_bandwidth:
            widgets.append("Low-bandwidth summary cards")
        direction = "rtl" if payload.rtl_enabled or payload.ui_language.lower() in {"ur", "urdu"} or payload.user_type.lower() == "urdu" else "ltr"
        font_size = payload.font_size if payload.font_size in {"small", "medium", "large", "xl"} else ("large" if payload.verbosity == "beginner" else "medium")
        glossary_terms = list(dict.fromkeys([*payload.glossary_seed_terms, *recommended[:5]]))
        offline_reading = [{"key": item, "cache_route": f"/offline/{item}", "status": "queued"} for item in payload.offline_items]
        data_export_uri = self._write_export(payload, recommended) if payload.data_action == "export" else None
        data_delete_receipt = f"delete-{uuid4().hex[:12]}" if payload.data_action == "delete" else None
        response = PersonalizationResponse(
            recommended_topics=recommended,
            home_feed=[f"Similar to your reading: {topic}" for topic in recommended[:3]],
            dashboard_widgets=widgets,
            glossary_terms=glossary_terms,
            weekly_digest=f"{payload.digest_frequency.title()} digest prepared with recent papers, alerts, and workspace updates.",
            scheduled_digest={
                "frequency": payload.digest_frequency,
                "channel": "email",
                "status": "scheduled",
                "next_run": "next-cycle",
            },
            onboarding_path=[f"Start as a {payload.user_type}", "Connect saved searches", "Choose verbosity preferences"],
            accessibility_profile={
                "direction": direction,
                "theme": payload.theme if payload.theme in {"dark", "light", "contrast"} else ("contrast" if payload.low_bandwidth else "dark"),
                "font_size": font_size,
                "font_family": "Atkinson Hyperlegible" if payload.dyslexia_friendly else "Resora Serif/Sans",
                "wcag_target": "2.1 AA",
            },
            urdu_ui={
                "enabled": direction == "rtl",
                "language": "ur" if direction == "rtl" else "en",
                "layout": "right-to-left" if direction == "rtl" else "left-to-right",
                "label_search": "تلاش" if direction == "rtl" else "Search",
            },
            font_controls={
                "size": font_size,
                "dyslexia_friendly": payload.dyslexia_friendly,
                "line_height": "relaxed",
                "letter_spacing": "wide" if payload.dyslexia_friendly else "normal",
            },
            tts_controls={
                "enabled": payload.tts_enabled,
                "scope": "any content",
                "voice_hint": "ur-PK" if direction == "rtl" else "en-US",
            },
            keyboard_navigation_map=["skip-to-content", "sidebar-nav", "command-search", "reader-actions", "toast-region"],
            screen_reader_landmarks=["banner", "navigation", "main", "complementary", "contentinfo"],
            wcag_aa_checklist={
                "keyboard_access": True,
                "screen_reader_labels": True,
                "high_contrast": True,
                "rtl_support": True,
                "focus_visible": True,
                "reduced_motion_safe": True,
            },
            contextual_help_tooltips={
                "search": "Use natural language, Boolean operators, voice, or image search.",
                "reader": "Choose beginner/expert summaries and right-click paragraphs for explanation.",
                "offline": "Saved papers and summaries are cached for PWA reading.",
                "privacy": "Export or delete your profile and workspace history anytime.",
            },
            color_blind_safe_palette={
                "primary": "#A84408",
                "background": "#000000",
                "text": "#FFFFFF",
                "warning": "#FFB000",
                "safe": "#56B4E9",
            },
            offline_reading_list=offline_reading,
            pwa_cache_manifest={
                "static_cache": ["index", "manifest", "icon", "shell-css"],
                "reading_cache": [item["key"] for item in offline_reading],
                "strategy": "cache-first for saved reading, network-first for live APIs",
                "max_items": max(25, len(offline_reading) + 10),
            },
            low_bandwidth_mode={
                "enabled": payload.low_bandwidth,
                "image_policy": "defer-nonessential-images",
                "summary_policy": "prefer-micro-summaries",
                "sync_policy": "batch-background-sync",
            },
            multi_device_sync={
                "device_count": len(payload.device_ids),
                "devices": payload.device_ids,
                "continuity_token": f"sync-{uuid4().hex[:10]}",
                "status": "ready",
            },
            customizable_dashboard={
                "selected_widgets": widgets,
                "layout": "compact" if payload.low_bandwidth else "research-command-center",
            },
            similar_to_read_feed=[f"Because you read '{item}', try {recommended[index % len(recommended)]}" for index, item in enumerate(payload.reading_history[:5])] if payload.reading_history else ["Start reading papers to personalize this feed."],
            ai_preferences={
                "verbosity": payload.verbosity,
                "default_answer_style": "step-by-step" if payload.verbosity == "beginner" else "concise evidence-first",
            },
            personal_glossary={term: f"Personal definition card for {term}" for term in glossary_terms[:8]},
            sync_status=f"{len(payload.offline_items)} offline items ready to sync" if payload.offline_items else "All devices synced",
            gdpr_actions=["Export my data", "Delete my workspace history", "Manage notification preferences"],
            data_export_uri=data_export_uri,
            data_delete_receipt=data_delete_receipt,
        )
        response.profile_snapshot_uri = self._persist_profile(response)
        return response

    def _write_export(self, payload: PersonalizationRequest, recommended: list[str]) -> str:
        self.store_dir.mkdir(parents=True, exist_ok=True)
        path = self.store_dir / f"data-export-{uuid4().hex[:12]}.json"
        path.write_text(
            PersonalizationExport(payload=payload.model_dump(), recommended_topics=recommended, exported_at=datetime.now(UTC).isoformat()).to_json(),
            encoding="utf-8",
        )
        return path.as_posix()

    def _persist_profile(self, response: PersonalizationResponse) -> str:
        self.store_dir.mkdir(parents=True, exist_ok=True)
        path = self.store_dir / f"profile-{uuid4().hex[:12]}.json"
        path.write_text(response.model_dump_json(indent=2), encoding="utf-8")
        return path.as_posix()


class PersonalizationExport:
    def __init__(self, payload: dict, recommended_topics: list[str], exported_at: str) -> None:
        self.payload = payload
        self.recommended_topics = recommended_topics
        self.exported_at = exported_at

    def to_json(self) -> str:
        import json

        return json.dumps(
            {
                "payload": self.payload,
                "recommended_topics": self.recommended_topics,
                "exported_at": self.exported_at,
            },
            indent=2,
        )
