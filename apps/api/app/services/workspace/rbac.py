from uuid import uuid4

from app.schemas.workspace import (
    WorkspaceCreateRequest,
    WorkspaceDetail,
    WorkspaceMember,
    WorkspaceSummary,
)


class WorkspaceService:
    _store: dict[str, WorkspaceDetail] = {}

    def __init__(self) -> None:
        self._default = WorkspaceDetail(
            workspace_id="default-lab",
            name="Default Research Lab",
            members=[
                WorkspaceMember(user_id="u1", email="owner@resora.local", role="owner"),
                WorkspaceMember(user_id="u2", email="editor@resora.local", role="editor"),
                WorkspaceMember(user_id="u3", email="viewer@resora.local", role="viewer"),
            ],
            projects=["Resora Core"],
            permissions=["read", "comment", "edit", "share", "manage"],
            share_capabilities=["guest-links", "expiring-review-links", "workspace-packets"],
            collaboration_modes=["comment-only", "editorial", "supervisor-review"],
            activity_summary={"papers": 24, "drafts": 5, "comments": 18, "tasks": 7},
            role_matrix={
                "owner": ["read", "comment", "edit", "share", "manage", "export"],
                "editor": ["read", "comment", "edit", "share", "export"],
                "viewer": ["read", "comment"],
            },
            guest_policy={"enabled": True, "default_permission": "comment", "expiry_days": 7, "approval_required": True},
            ai_usage_quota_by_role={"owner": 1000, "editor": 600, "viewer": 150},
            notification_channels=["email", "slack", "discord"],
            shared_folders=["Core Papers", "Drafts", "Supervisor Notes"],
            research_packet_exports=["pdf", "docx", "zip"],
            template_origin="default-research-lab",
            default_review_mode="comment-only",
            dashboards=["team-overview", "research-pipeline", "audit-log"],
            versioning_enabled=True,
            audit_enabled=True,
        )
        cls = type(self)
        if not cls._store:
            cls._store[self._default.workspace_id] = self._default

    def list_workspaces(self) -> list[WorkspaceSummary]:
        return [
            WorkspaceSummary(
                workspace_id=workspace.workspace_id,
                name=workspace.name,
                member_count=len(workspace.members),
                project_count=len(workspace.projects),
                roles=sorted({member.role for member in workspace.members}),
                default_review_mode=workspace.default_review_mode,
                template_origin=workspace.template_origin,
                alerts_enabled="share" in workspace.permissions,
            )
            for workspace in type(self)._store.values()
        ]

    def get_workspace(self, workspace_id: str) -> WorkspaceDetail:
        stored = type(self)._store.get(workspace_id)
        if stored:
            return stored
        ad_hoc = WorkspaceDetail(
            workspace_id=workspace_id,
            name="Ad Hoc Workspace",
            members=[WorkspaceMember(user_id="u1", email="owner@resora.local", role="owner")],
            projects=[],
            permissions=["read", "edit"],
            share_capabilities=["guest-links"],
            collaboration_modes=["comment-only"],
            activity_summary={"papers": 0, "drafts": 0, "comments": 0, "tasks": 0},
            role_matrix={"owner": ["read", "edit"], "viewer": ["read"]},
            guest_policy={"enabled": True, "default_permission": "view", "expiry_days": 7, "approval_required": False},
            ai_usage_quota_by_role={"owner": 300, "viewer": 75},
            notification_channels=["email"],
            shared_folders=["Inbox"],
            research_packet_exports=["zip"],
            template_origin="blank",
            default_review_mode="comment-only",
            dashboards=["team-overview"],
            versioning_enabled=True,
            audit_enabled=True,
        )
        type(self)._store[workspace_id] = ad_hoc
        return ad_hoc

    def create_workspace(self, payload: WorkspaceCreateRequest) -> WorkspaceDetail:
        workspace_id = f"ws-{uuid4().hex[:8]}"
        members = [WorkspaceMember(user_id="u1", email=payload.owner_email, role="owner")]
        members.extend(
            WorkspaceMember(user_id=f"u{index + 2}", email=email, role="editor")
            for index, email in enumerate(payload.member_emails[:10])
        )
        detail = WorkspaceDetail(
            workspace_id=workspace_id,
            name=payload.name,
            members=members,
            projects=["Launch Plan"],
            permissions=["read", "comment", "edit", "share", "manage"],
            share_capabilities=["guest-links", "expiring-review-links", "workspace-packets", "research-archives"],
            collaboration_modes=["comment-only", "editorial", "supervisor-review", payload.review_mode],
            activity_summary={"papers": 0, "drafts": 0, "comments": 0, "tasks": 0},
            role_matrix={
                "owner": ["read", "comment", "edit", "share", "manage", "export"],
                "editor": ["read", "comment", "edit", "share", "export"],
                "viewer": ["read", "comment"],
            },
            guest_policy={"enabled": True, "default_permission": "comment", "expiry_days": 7, "approval_required": True},
            ai_usage_quota_by_role={"owner": 1000, "editor": 600, "viewer": 150},
            notification_channels=payload.notification_channels,
            shared_folders=payload.shared_folders,
            research_packet_exports=["pdf", "docx", "latex", "zip"],
            template_origin=payload.template_origin,
            default_review_mode=payload.review_mode,
            dashboards=["team-overview", "research-pipeline", "audit-log", "usage-monitor"],
            versioning_enabled=True,
            audit_enabled=True,
        )
        type(self)._store[workspace_id] = detail
        return detail
