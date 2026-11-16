"""Teams: members and roles, invite links, shared projects, comments with @mentions, supervisor reviews,
activity log, notifications and pooled usage."""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from app.api.deps import AuthContext, get_auth_context
from app.core.config import settings
from app.services.teams import store
from app.services.teams.store import TeamError

router = APIRouter()


def _user(auth: AuthContext) -> str:
    if (settings.deployment_stage.lower() == "production" and not auth.verified) or not auth.user_id or auth.user_id == "anonymous":
        raise HTTPException(status_code=401, detail={"code": "sign_in_required"})
    return auth.user_id


async def _run(call):
    def guarded():
        try:
            return call()
        except TeamError as error:
            raise HTTPException(status_code=error.status, detail={"code": error.code}) from error

    return await asyncio.to_thread(guarded)


class TeamCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=500)
    display_name: str = Field(default="Owner", max_length=80)


class TeamUpdate(BaseModel):
    name: str | None = Field(default=None, max_length=120)
    description: str | None = Field(default=None, max_length=500)


class MemberUpdate(BaseModel):
    role: str | None = None
    display_name: str | None = Field(default=None, max_length=80)


class InviteCreate(BaseModel):
    role: str = "member"
    email: str | None = Field(default=None, max_length=254)
    days: int = Field(default=7, ge=1, le=30)
    max_uses: int = Field(default=1, ge=1, le=50)


class InviteAccept(BaseModel):
    display_name: str = Field(default="Member", max_length=80)


class ProjectBody(BaseModel):
    name: str | None = Field(default=None, max_length=160)
    description: str | None = Field(default=None, max_length=1000)


class PapersAdd(BaseModel):
    item_ids: list[str] = Field(default_factory=list, max_length=200)
    papers: list[dict] = Field(default_factory=list, max_length=200)


class PaperUpdate(BaseModel):
    status: str | None = None
    assignee_id: str | None = None
    clear_assignee: bool = False


class CommentCreate(BaseModel):
    target_type: str = Field(pattern="^(project|paper|review)$")
    target_id: str
    body: str = Field(min_length=1, max_length=5000)
    parent_id: str | None = None


class CommentUpdate(BaseModel):
    body: str | None = Field(default=None, max_length=5000)
    delete: bool = False


class ReviewCreate(BaseModel):
    document_id: str
    reviewer_id: str | None = None


class ReviewDecision(BaseModel):
    status: str = Field(pattern="^(approved|changes_requested)$")
    note: str | None = Field(default=None, max_length=4000)


class TransferBody(BaseModel):
    user_id: str


class ReadBody(BaseModel):
    ids: list[str] | None = None


# ---------------------------------------------------------------- notifications (before /{team_id} routes)

@router.get("/notifications/me")
async def my_notifications(unread_only: bool = False, auth: AuthContext = Depends(get_auth_context)) -> dict:
    user = _user(auth)
    return {"notifications": await _run(lambda: store.notifications(user, unread_only=unread_only))}


@router.post("/notifications/read")
async def read_notifications(payload: ReadBody, auth: AuthContext = Depends(get_auth_context)) -> dict:
    user = _user(auth)
    return {"updated": await _run(lambda: store.mark_read(user, payload.ids))}


@router.get("/invites/{token}")
async def preview_invite(token: str) -> dict:
    return await _run(lambda: store.preview_invite(token))


@router.post("/invites/{token}/accept")
async def accept_invite(token: str, payload: InviteAccept, auth: AuthContext = Depends(get_auth_context)) -> dict:
    user = _user(auth)
    return await _run(lambda: store.accept_invite(user, token, display_name=payload.display_name))


# ---------------------------------------------------------------- teams

@router.get("")
async def list_teams(auth: AuthContext = Depends(get_auth_context)) -> dict:
    user = _user(auth)
    return {"teams": await _run(lambda: store.list_teams(user))}


@router.post("", status_code=201)
async def create_team(payload: TeamCreate, auth: AuthContext = Depends(get_auth_context)) -> dict:
    user = _user(auth)
    return await _run(lambda: store.create_team(user, name=payload.name, description=payload.description, display_name=payload.display_name))


@router.get("/{team_id}")
async def team(team_id: str, auth: AuthContext = Depends(get_auth_context)) -> dict:
    user = _user(auth)
    detail = await _run(lambda: store.team_detail(user, team_id))
    from app.services.billing import service as billing

    sub = await asyncio.to_thread(billing.subscription, detail["owner_id"])
    detail["subscription"] = sub if sub and sub.get("team_id") == team_id else None
    return detail


@router.patch("/{team_id}")
async def update_team(team_id: str, payload: TeamUpdate, auth: AuthContext = Depends(get_auth_context)) -> dict:
    user = _user(auth)
    return await _run(lambda: store.update_team(user, team_id, name=payload.name, description=payload.description))


@router.delete("/{team_id}", status_code=204)
async def delete_team(team_id: str, auth: AuthContext = Depends(get_auth_context)) -> None:
    user = _user(auth)
    await _run(lambda: store.delete_team(user, team_id))


@router.post("/{team_id}/transfer")
async def transfer(team_id: str, payload: TransferBody, auth: AuthContext = Depends(get_auth_context)) -> dict:
    user = _user(auth)
    return await _run(lambda: store.transfer_ownership(user, team_id, payload.user_id))


@router.patch("/{team_id}/members/{member_id}")
async def update_member(team_id: str, member_id: str, payload: MemberUpdate, auth: AuthContext = Depends(get_auth_context)) -> dict:
    user = _user(auth)
    return await _run(lambda: store.update_member(user, team_id, member_id, role=payload.role, display_name=payload.display_name))


@router.delete("/{team_id}/members/{member_id}", status_code=204)
async def remove_member(team_id: str, member_id: str, auth: AuthContext = Depends(get_auth_context)) -> None:
    user = _user(auth)
    await _run(lambda: store.remove_member(user, team_id, member_id))


@router.get("/{team_id}/invites")
async def invites(team_id: str, auth: AuthContext = Depends(get_auth_context)) -> dict:
    user = _user(auth)
    return {"invites": await _run(lambda: store.list_invites(user, team_id))}


@router.post("/{team_id}/invites", status_code=201)
async def create_invite(team_id: str, payload: InviteCreate, auth: AuthContext = Depends(get_auth_context)) -> dict:
    user = _user(auth)
    return await _run(lambda: store.create_invite(user, team_id, role=payload.role, email=payload.email, days=payload.days, max_uses=payload.max_uses))


@router.delete("/{team_id}/invites/{invite_id}", status_code=204)
async def revoke_invite(team_id: str, invite_id: str, auth: AuthContext = Depends(get_auth_context)) -> None:
    user = _user(auth)
    await _run(lambda: store.revoke_invite(user, team_id, invite_id))


# ---------------------------------------------------------------- projects

@router.get("/{team_id}/projects")
async def projects(team_id: str, auth: AuthContext = Depends(get_auth_context)) -> dict:
    user = _user(auth)
    return {"projects": await _run(lambda: store.list_projects(user, team_id))}


@router.post("/{team_id}/projects", status_code=201)
async def create_project(team_id: str, payload: ProjectBody, auth: AuthContext = Depends(get_auth_context)) -> dict:
    user = _user(auth)
    return await _run(lambda: store.create_project(user, team_id, name=payload.name or "", description=payload.description))


@router.get("/{team_id}/projects/{project_id}")
async def project(team_id: str, project_id: str, auth: AuthContext = Depends(get_auth_context)) -> dict:
    user = _user(auth)
    return await _run(lambda: store.project_detail(user, team_id, project_id))


@router.patch("/{team_id}/projects/{project_id}")
async def update_project(team_id: str, project_id: str, payload: ProjectBody, auth: AuthContext = Depends(get_auth_context)) -> dict:
    user = _user(auth)
    return await _run(lambda: store.update_project(user, team_id, project_id, name=payload.name, description=payload.description))


@router.delete("/{team_id}/projects/{project_id}", status_code=204)
async def delete_project(team_id: str, project_id: str, auth: AuthContext = Depends(get_auth_context)) -> None:
    user = _user(auth)
    await _run(lambda: store.delete_project(user, team_id, project_id))


@router.post("/{team_id}/projects/{project_id}/papers")
async def add_papers(team_id: str, project_id: str, payload: PapersAdd, auth: AuthContext = Depends(get_auth_context)) -> dict:
    """Add papers from the caller's own Library (item_ids) and/or as plain metadata (e.g. from Search)."""
    user = _user(auth)
    papers = list(payload.papers)
    if payload.item_ids:
        from app.services.library.store import LibraryStore

        wanted = set(payload.item_ids)
        items = await asyncio.to_thread(lambda: [item for item in LibraryStore().list_items(user) if item.get("id") in wanted])
        papers += [{k: item.get(k) for k in ("title", "authors", "year", "venue", "doi", "url", "abstract")} for item in items]
    return await _run(lambda: store.add_papers(user, team_id, project_id, papers))


@router.patch("/{team_id}/projects/{project_id}/papers/{paper_id}")
async def update_paper(team_id: str, project_id: str, paper_id: str, payload: PaperUpdate, auth: AuthContext = Depends(get_auth_context)) -> dict:
    user = _user(auth)
    return await _run(lambda: store.update_paper(user, team_id, project_id, paper_id, status=payload.status, assignee_id=payload.assignee_id, clear_assignee=payload.clear_assignee))


@router.delete("/{team_id}/projects/{project_id}/papers/{paper_id}", status_code=204)
async def remove_paper(team_id: str, project_id: str, paper_id: str, auth: AuthContext = Depends(get_auth_context)) -> None:
    user = _user(auth)
    await _run(lambda: store.remove_paper(user, team_id, project_id, paper_id))


# ---------------------------------------------------------------- comments

@router.get("/{team_id}/comments")
async def comments(team_id: str, target_type: str, target_id: str, auth: AuthContext = Depends(get_auth_context)) -> dict:
    user = _user(auth)
    return {"comments": await _run(lambda: store.list_comments(user, team_id, target_type, target_id))}


@router.post("/{team_id}/comments", status_code=201)
async def add_comment(team_id: str, payload: CommentCreate, auth: AuthContext = Depends(get_auth_context)) -> dict:
    user = _user(auth)
    return await _run(lambda: store.add_comment(user, team_id, target_type=payload.target_type, target_id=payload.target_id, body=payload.body, parent_id=payload.parent_id))


@router.patch("/{team_id}/comments/{comment_id}", status_code=204)
async def edit_comment(team_id: str, comment_id: str, payload: CommentUpdate, auth: AuthContext = Depends(get_auth_context)) -> None:
    user = _user(auth)
    await _run(lambda: store.edit_comment(user, team_id, comment_id, body=payload.body, delete=payload.delete))


# ---------------------------------------------------------------- supervisor reviews

@router.get("/{team_id}/reviews")
async def reviews(team_id: str, auth: AuthContext = Depends(get_auth_context)) -> dict:
    user = _user(auth)
    return {"reviews": await _run(lambda: store.list_reviews(user, team_id))}


@router.post("/{team_id}/reviews", status_code=201)
async def request_review(team_id: str, payload: ReviewCreate, auth: AuthContext = Depends(get_auth_context)) -> dict:
    """Snapshot one of the caller's Write documents (with its references) and ask a supervisor to review it."""
    user = _user(auth)
    from app.services.library.store import LibraryNotFound
    from app.services.write.exporter import to_markdown
    from app.services.write.store import WriteStore

    def snapshot():
        try:
            doc = WriteStore().get_document(user, payload.document_id)
        except LibraryNotFound as error:
            raise TeamError("not_found", 404) from error
        return doc, to_markdown(doc)

    doc, text = await _run(snapshot)
    return await _run(lambda: store.request_review(user, team_id, document_id=doc["id"], title=doc["title"], snapshot=text, reviewer_id=payload.reviewer_id))


@router.get("/{team_id}/reviews/{review_id}")
async def review(team_id: str, review_id: str, auth: AuthContext = Depends(get_auth_context)) -> dict:
    user = _user(auth)
    return await _run(lambda: store.review_detail(user, team_id, review_id))


@router.post("/{team_id}/reviews/{review_id}/decision")
async def decide(team_id: str, review_id: str, payload: ReviewDecision, auth: AuthContext = Depends(get_auth_context)) -> dict:
    user = _user(auth)
    return await _run(lambda: store.decide_review(user, team_id, review_id, status=payload.status, note=payload.note))


# ---------------------------------------------------------------- activity + usage

@router.get("/{team_id}/activity")
async def team_activity(team_id: str, limit: int = 100, auth: AuthContext = Depends(get_auth_context)) -> dict:
    user = _user(auth)
    return {"activity": await _run(lambda: store.activity(user, team_id, limit))}


@router.get("/{team_id}/usage")
async def team_usage(team_id: str, request: Request, auth: AuthContext = Depends(get_auth_context)) -> dict:
    user = _user(auth)
    detail = await _run(lambda: store.team_detail(user, team_id))
    from app.services.billing import service as billing
    from app.services.credits.service import get_credit_service

    sub = await asyncio.to_thread(billing.subscription, detail["owner_id"])
    pooled = bool(sub and sub.get("team_id") == team_id)
    plan = sub["plan"] if pooled else "free"
    seats = int(sub["seats"]) if pooled else 1
    usage = await asyncio.to_thread(get_credit_service().usage, f"team:{team_id}", plan) if pooled else None
    if usage:  # the team key itself is not resolved by billing, so scale the limits by seats here
        for window in usage["windows"]:
            window["limit"] *= seats
            window["remaining"] = max(0, window["limit"] - window["used"])
            window["percent"] = round(min(1.0, window["used"] / window["limit"]), 3) if window["limit"] else 0.0
    return {"pooled": pooled, "plan": plan, "seats": seats, "members": len(detail["members"]), "usage": usage, "subscription": sub if pooled else None}
