from datetime import UTC, datetime
import json
import os
from pathlib import Path
from uuid import uuid4
import zipfile

from app.schemas.collaboration import (
    AIContentAuditEntry,
    CollaborationRequest,
    CollaborationResponse,
    ConcurrentEditState,
    DigestDeliveryReceipt,
    MemberPresence,
    ReviewCheckpoint,
    ShareLinkSummary,
    TaskAssignmentSummary,
)


class CollaborationService:
    def __init__(self) -> None:
        self.store_dir = Path(os.getenv("RESORA_WORKSPACE_STORE_DIR", "storage/workspaces"))

    def summarize(self, payload: CollaborationRequest) -> CollaborationResponse:
        generated_at = datetime.now(UTC).isoformat()
        activity_feed = [f"Comment thread updated for {thread.resource_type}:{thread.resource_id}" for thread in payload.comments]
        activity_feed.extend(f"Task '{task.title}' assigned to {task.assignee}" for task in payload.tasks)
        activity_feed.extend(
            f"Shared folder '{folder}' synced for workspace taxonomy"
            for folder in payload.shared_folders[:3]
        )
        notifications = [f"Mention alert for {mention}" for mention in payload.mentions]
        notifications.extend(
            f"Digest scheduled for {channel}"
            for channel in payload.digest_channels[:3]
        )
        team_dashboard = {
            "members_active": max(1, len(payload.mentions)),
            "open_tasks": sum(1 for task in payload.tasks if task.status == "open"),
            "comment_threads": len(payload.comments),
            "guest_review_links": min(3, len(payload.comments)) if payload.guest_review_enabled else 0,
        }
        task_board = {
            "open": sum(1 for task in payload.tasks if task.status == "open"),
            "in_review": sum(1 for task in payload.tasks if task.status == "in_review"),
            "completed": sum(1 for task in payload.tasks if task.status == "done"),
        }
        member_names = sorted(set(payload.mentions + [task.assignee for task in payload.tasks]))
        member_presence = [
            MemberPresence(
                member=name,
                status="active" if name in payload.mentions else "async",
                assigned_tasks=sum(1 for task in payload.tasks if task.assignee == name),
            )
            for name in member_names
        ]
        task_assignments = [
            TaskAssignmentSummary(
                assignee=name,
                open_tasks=sum(1 for task in payload.tasks if task.assignee == name and task.status == "open"),
                in_review_tasks=sum(1 for task in payload.tasks if task.assignee == name and task.status == "in_review"),
                overdue_risk=sum(1 for task in payload.tasks if task.assignee == name and (task.due_in_days or 99) <= 2),
            )
            for name in member_names
        ]
        review_checkpoints = [
            ReviewCheckpoint(label="Evidence pass", status="ready", owner="editor", checkpoint_id=f"chk-{uuid4().hex[:8]}"),
            ReviewCheckpoint(label="Supervisor review", status=payload.review_mode, owner="supervisor", checkpoint_id=f"chk-{uuid4().hex[:8]}"),
            ReviewCheckpoint(label="Export packet", status="ready" if payload.export_packet else "queued", owner="owner", checkpoint_id=f"chk-{uuid4().hex[:8]}"),
        ]
        share_links = [
            ShareLinkSummary(
                resource_type=thread.resource_type,
                token=f"{thread.resource_type}-{thread.resource_id}-share",
                permission="comment" if payload.review_mode == "comment-only" else "edit",
                expires_in_days=payload.share_expiry_days,
            )
            for thread in payload.comments[:3]
        ]
        collaborator_roles = payload.collaborator_roles or {
            name: ("supervisor" if "supervisor" in name.lower() else "editor")
            for name in member_names
        }
        role_summary = {
            "owner": 1,
            "editor": max(1, len([role for role in collaborator_roles.values() if role == "editor"])),
            "viewer": max(1, len(payload.mentions)),
        }
        review_threads_by_resource = {
            f"{thread.resource_type}:{thread.resource_id}": len(thread.comments)
            for thread in payload.comments
        }
        mention_directory = {mention: collaborator_roles.get(mention, "viewer") for mention in payload.mentions}
        quota_defaults = {"owner": 1000, "editor": 600, "viewer": 150, "supervisor": 250}
        ai_usage_quotas = {**quota_defaults, **payload.ai_quota_overrides}
        digest_receipts = self._digest_receipts(payload)
        ai_audit_log = self._ai_audit_log(payload, generated_at)
        concurrent_state = self._concurrent_edit_state(payload)
        packet_contents = ["papers", "summaries", "comments", "tasks", "audit-log", "review-checkpoints", "share-links", "meeting-notes", "usage-quotas"]
        base_response = CollaborationResponse(
            activity_feed=activity_feed or ["Workspace activity feed initialized."],
            notifications=notifications or ["No pending mention notifications."],
            team_dashboard=team_dashboard,
            supervisor_mode=f"{payload.review_mode} review enabled",
            research_packet_summary=f"Workspace {payload.workspace_id} can export a research packet with comments, tasks, selected papers, and review checkpoints.",
            guest_link=f"guest-{payload.workspace_id}",
            workspace_analytics={"mentions": len(payload.mentions), "tasks": len(payload.tasks), "threads": len(payload.comments)},
            concurrency_strategy=concurrent_state.strategy,
            meeting_note_links=[f"Map meeting note to {note}" for note in payload.meeting_notes[:3]] or [f"Map meeting note to {thread.resource_id}" for thread in payload.comments[:3]],
            digests=[f"{channel.title()} digest ready" for channel in payload.digest_channels],
            ai_usage_quotas=ai_usage_quotas,
            audit_summary="AI-generated changes remain visible in the workspace audit trail, including review-mode edits, share-link actions, and task reassignments.",
            template_workspace=f"{payload.template_name} template cloned successfully.",
            share_links=share_links or [ShareLinkSummary(resource_type="workspace", token=f"{payload.workspace_id}-share", permission="view", expires_in_days=payload.share_expiry_days)],
            task_board=task_board,
            member_presence=member_presence or [MemberPresence(member="owner", status="active", assigned_tasks=0)],
            task_assignments=task_assignments or [TaskAssignmentSummary(assignee="owner", open_tasks=0, in_review_tasks=0, overdue_risk=0)],
            review_checkpoints=review_checkpoints,
            role_summary=role_summary,
            collaborator_roles=collaborator_roles,
            shared_folder_summary=payload.shared_folders or ["Shared Reading Queue", "Supervisor Notes"],
            guest_review_policy={
                "enabled": payload.guest_review_enabled,
                "expiry_days": payload.share_expiry_days,
                "review_mode": payload.review_mode,
            },
            review_threads_by_resource=review_threads_by_resource,
            mention_directory=mention_directory,
            checkpoint_export_status={
                "research_packet": "ready",
                "draft_checkpoint": "ready" if payload.comments else "pending",
                "audit_log": "attached",
            },
            packet_contents=packet_contents,
            realtime_channels=[f"workspace:{payload.workspace_id}:presence", f"workspace:{payload.workspace_id}:document", f"workspace:{payload.workspace_id}:comments"],
            inline_comment_threads=payload.comments,
            digest_delivery_receipts=digest_receipts,
            ai_content_audit_log=ai_audit_log,
            concurrent_edit_state=concurrent_state,
            template_workspace_options=["default-research-lab", "systematic-review", "thesis-supervision", "grant-writing", "course-project"],
            rbac_matrix={
                "owner": ["read", "comment", "edit", "share", "manage", "export", "audit"],
                "editor": ["read", "comment", "edit", "share", "export"],
                "supervisor": ["read", "comment", "approve"],
                "viewer": ["read", "comment"],
            },
            generated_at=generated_at,
        )

        packet = self._write_research_packet(payload, base_response) if payload.export_packet else None
        if packet:
            base_response.research_packet_archive_uri = packet["uri"]
            base_response.research_packet_byte_size = packet["byte_size"]
            base_response.review_checkpoints[-1].storage_uri = packet["uri"]
        snapshot = self._persist_snapshot(payload, base_response)
        base_response.workspace_snapshot_uri = snapshot
        return base_response

    def _digest_receipts(self, payload: CollaborationRequest) -> list[DigestDeliveryReceipt]:
        targets = {
            "slack": "#resora-research",
            "discord": "resora-lab",
            "email": "workspace-members",
        }
        return [
            DigestDeliveryReceipt(
                channel=channel,
                status="queued",
                target=targets.get(channel, "custom-webhook"),
                message=f"{channel.title()} digest queued for workspace {payload.workspace_id}.",
            )
            for channel in payload.digest_channels
        ]

    def _ai_audit_log(self, payload: CollaborationRequest, generated_at: str) -> list[AIContentAuditEntry]:
        entries = []
        for index, event in enumerate(payload.ai_generated_events or [{"actor": "resora", "action": "workspace-summary", "resource_id": payload.workspace_id}], start=1):
            entries.append(
                AIContentAuditEntry(
                    event_id=f"audit-{index}-{uuid4().hex[:6]}",
                    actor=event.get("actor", "resora"),
                    action=event.get("action", "ai-generated-content"),
                    resource_id=event.get("resource_id", payload.workspace_id),
                    disclosure_required=True,
                    timestamp=generated_at,
                )
            )
        return entries

    def _concurrent_edit_state(self, payload: CollaborationRequest) -> ConcurrentEditState:
        text = payload.live_document_text or "Workspace collaborative draft initialized."
        conflict_count = 0
        for edit in payload.concurrent_edits:
            operation = edit.get("operation", "append")
            value = edit.get("text", "")
            if operation == "append":
                text = f"{text}\n{value}".strip()
            elif operation == "replace":
                target = edit.get("target", "")
                if target and target in text:
                    text = text.replace(target, value, 1)
                else:
                    conflict_count += 1
                    text = f"{text}\n[conflict-note] {value}".strip()
            else:
                conflict_count += 1
        return ConcurrentEditState(
            strategy="operation-log CRDT-style merge with conflict annotations",
            document_version=f"docv-{uuid4().hex[:10]}",
            merged_text=text,
            operations_applied=len(payload.concurrent_edits),
            conflict_count=conflict_count,
        )

    def _write_research_packet(self, payload: CollaborationRequest, response: CollaborationResponse) -> dict[str, str | int]:
        packet_dir = self.store_dir / payload.workspace_id
        packet_dir.mkdir(parents=True, exist_ok=True)
        archive_path = packet_dir / f"research-packet-{uuid4().hex[:10]}.zip"
        manifest = {
            "workspace_id": payload.workspace_id,
            "packet_contents": response.packet_contents,
            "share_links": [item.model_dump() for item in response.share_links],
            "checkpoints": [item.model_dump() for item in response.review_checkpoints],
            "generated_at": response.generated_at,
        }
        with zipfile.ZipFile(archive_path, "w", zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("manifest.json", json.dumps(manifest, indent=2))
            archive.writestr("comments.json", json.dumps([item.model_dump() for item in payload.comments], indent=2))
            archive.writestr("tasks.json", json.dumps([item.model_dump() for item in payload.tasks], indent=2))
            archive.writestr("ai-audit-log.json", json.dumps([item.model_dump() for item in response.ai_content_audit_log], indent=2))
            archive.writestr("meeting-notes.json", json.dumps(payload.meeting_notes, indent=2))
            archive.writestr("collaborative-document.txt", response.concurrent_edit_state.merged_text if response.concurrent_edit_state else "")
        return {"uri": archive_path.as_posix(), "byte_size": archive_path.stat().st_size}

    def _persist_snapshot(self, payload: CollaborationRequest, response: CollaborationResponse) -> str:
        snapshot_dir = self.store_dir / payload.workspace_id
        snapshot_dir.mkdir(parents=True, exist_ok=True)
        path = snapshot_dir / f"workspace-snapshot-{uuid4().hex[:10]}.json"
        path.write_text(response.model_dump_json(indent=2), encoding="utf-8")
        return path.as_posix()
