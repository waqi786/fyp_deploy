import base64
from datetime import UTC, datetime

from app.schemas.mobile import MobileExperienceRequest, MobileExperienceResponse


class MobileExperienceService:
    def build(self, payload: MobileExperienceRequest) -> MobileExperienceResponse:
        generated_at = datetime.now(UTC).isoformat()
        offline_cache_plan = [f"paper:{paper_id}" for paper_id in payload.saved_papers]
        offline_cache_plan.extend(f"summary:{summary_id}" for summary_id in payload.saved_summaries)
        push_notifications = [f"Saved-search alert ready for '{query}'" for query in payload.saved_searches[:5]] if payload.push_enabled else ["Push notifications disabled on this device."]
        triage_queue = [f"Swipe review: {paper_id}" for paper_id in payload.saved_papers[:10]]
        offline_bundles = [
            {"name": "saved-papers", "items": len(payload.saved_papers), "priority": "high"},
            {"name": "saved-summaries", "items": len(payload.saved_summaries), "priority": "high"},
            {"name": "workspace-shell", "items": 1, "priority": "medium"},
        ]
        device_layout = self._device_layout(payload.device_type)
        qr_payloads = {
            "workspace": self._qr_stub(f"resora://workspace/{payload.workspace_id}"),
            "first_paper": self._qr_stub(f"resora://paper/{payload.saved_papers[0]}") if payload.saved_papers else self._qr_stub("resora://paper/none"),
        }
        return MobileExperienceResponse(
            installable=True,
            pwa_install_prompt={
                "available": True,
                "display_mode": "standalone",
                "install_text": "Install Resora for offline research reading.",
            },
            offline_cache_plan=offline_cache_plan or ["saved-searches", "dashboard-shell"],
            offline_bundles=offline_bundles,
            mobile_voice_mode="voice-first chat enabled" if payload.voice_enabled else "voice chat disabled",
            push_notifications=push_notifications or ["Push alerts available for saved-search matches."],
            push_categories=["saved-search-alerts", "workspace-mentions", "review-deadlines"] if payload.push_enabled else ["disabled"],
            low_data_mode="compressed summaries and deferred image loading enabled" if payload.low_data_mode else "standard bandwidth profile",
            swipe_triage_queue=triage_queue or ["Swipe review queue is empty."],
            swipe_triage_actions=[
                {"gesture": "swipe-right", "action": "save-to-library"},
                {"gesture": "swipe-left", "action": "skip"},
                {"gesture": "swipe-up", "action": "summarize"},
                {"gesture": "long-press", "action": "open-pdf-viewer"},
            ] if payload.triage_mode == "swipe" else [{"gesture": "tap", "action": "open"}],
            background_sync_status=f"{len(payload.offline_actions)} offline actions queued for sync" if payload.offline_actions else "Offline action queue is clear",
            sync_manifest={
                "queued_actions": len(payload.offline_actions),
                "retry_policy": "exponential-backoff",
                "next_sync_mode": "wifi-preferred" if payload.low_data_mode else "immediate-when-online",
            },
            cache_policy={
                "mode": "low-data" if payload.low_data_mode else "standard",
                "max_items": max(25, len(offline_cache_plan) + 10),
                "evicts_after_hours": 72 if payload.low_data_mode else 48,
            },
            pdf_mobile_features=[
                "tap-to-explain figures",
                "single-column readability mode",
                "sticky citation toolbar",
                "pinch zoom with figure focus",
            ],
            mobile_pdf_viewer_state={
                "pdf_id": payload.pdf_id or (payload.saved_papers[0] if payload.saved_papers else "none"),
                "mode": "mobile-optimized",
                "tap_to_explain": True,
                "offline_available": bool(payload.saved_papers or payload.saved_summaries),
            },
            continuity_status="Cross-device continuity token ready for mobile, tablet, and desktop handoff.",
            continuity_payload={
                "handoff_token": self._qr_stub(f"handoff:{payload.workspace_id}:{payload.device_type}"),
                "source_device": payload.last_device or payload.device_type,
                "target_devices": ["phone", "tablet", "desktop"],
            },
            device_layout=device_layout,
            offline_readiness_score=self._offline_readiness_score(payload),
            qr_share_payloads=qr_payloads,
            qr_share_metadata={
                "workspace": {"type": "workspace", "deep_link": f"resora://workspace/{payload.workspace_id}"},
                "first_paper": {"type": "paper", "deep_link": f"resora://paper/{payload.saved_papers[0] if payload.saved_papers else 'none'}"},
            },
            cross_platform_targets=["ios-pwa", "android-pwa", "tablet", "desktop-browser"],
            generated_at=generated_at,
        )

    def _qr_stub(self, value: str) -> str:
        return base64.urlsafe_b64encode(value.encode("utf-8")).decode("utf-8")

    def _device_layout(self, device_type: str) -> str:
        layouts = {
            "phone": "stacked-mobile-layout",
            "tablet": "split-pane-tablet-layout",
            "desktop": "three-column-continuity-layout",
        }
        return layouts.get(device_type, "stacked-mobile-layout")

    def _offline_readiness_score(self, payload: MobileExperienceRequest) -> float:
        score = 0.5
        if payload.saved_papers:
            score += 0.15
        if payload.saved_summaries:
            score += 0.1
        if payload.offline_actions:
            score += 0.1
        if payload.low_data_mode:
            score += 0.1
        if payload.push_enabled:
            score += 0.05
        return round(min(1.0, score), 2)
