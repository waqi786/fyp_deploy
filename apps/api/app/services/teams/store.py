"""Teams: workspaces with roles, invite links, shared projects, comments with @mentions, supervisor reviews,
notifications and an audit log (master prompt Part 17, Vision "work together").

Roles (highest first) and what they can do:
  owner       everything, including deleting the team, transferring ownership and paying for the team plan
  admin       manage members, invites and projects
  supervisor  everything a member can, plus deciding review requests (approve / request changes)
  member      add papers to shared projects, comment, request reviews
  viewer      read only
Every query is scoped to a team the caller belongs to; another team's ids behave as if they did not exist.
Invite tokens are random, shown once and stored only as a SHA-256 hash.
"""

from __future__ import annotations

import hashlib
import json
import re
import secrets
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from app.services.sqlstore import database, now_iso

ROLES = ("owner", "admin", "supervisor", "member", "viewer")
RANK = {role: len(ROLES) - index for index, role in enumerate(ROLES)}
PAPER_STATUSES = ("to_read", "reading", "done")
REVIEW_STATUSES = ("pending", "approved", "changes_requested")
MAX_TEAMS_PER_USER = 20
MAX_MEMBERS = 200

SCHEMA = [
    """create table if not exists teams (
        id text primary key, name text not null, description text, owner_id text not null, created_at text not null, updated_at text not null)""",
    """create table if not exists team_members (
        team_id text not null, user_id text not null, role text not null, display_name text not null, joined_at text not null,
        primary key (team_id, user_id))""",
    "create index if not exists ix_team_members_user on team_members (user_id)",
    """create table if not exists team_invites (
        id text primary key, team_id text not null, token_hash text not null unique, role text not null, email text,
        created_by text not null, created_at text not null, expires_at text not null, max_uses integer not null default 1,
        uses integer not null default 0, revoked integer not null default 0)""",
    """create table if not exists team_projects (
        id text primary key, team_id text not null, name text not null, description text, created_by text not null,
        created_at text not null, updated_at text not null)""",
    """create table if not exists team_project_papers (
        id text primary key, project_id text not null, team_id text not null, paper_key text not null, title text not null,
        authors text not null, year integer, venue text, doi text, url text, abstract text, status text not null,
        assignee_id text, added_by text not null, added_at text not null, unique (project_id, paper_key))""",
    """create table if not exists team_comments (
        id text primary key, team_id text not null, target_type text not null, target_id text not null, author_id text not null,
        body text not null, mentions text not null, parent_id text, created_at text not null, edited_at text, deleted integer not null default 0)""",
    "create index if not exists ix_team_comments_target on team_comments (team_id, target_type, target_id)",
    """create table if not exists team_reviews (
        id text primary key, team_id text not null, document_id text not null, title text not null, snapshot text not null,
        requested_by text not null, reviewer_id text, status text not null, decision_note text, created_at text not null,
        decided_at text, decided_by text, round integer not null default 1)""",
    """create table if not exists team_activity (
        id text primary key, team_id text not null, actor_id text not null, action text not null, target_type text,
        target_id text, summary text not null, created_at text not null)""",
    "create index if not exists ix_team_activity_team on team_activity (team_id, created_at)",
    """create table if not exists team_notifications (
        id text primary key, user_id text not null, team_id text not null, kind text not null, payload text not null,
        is_read integer not null default 0, created_at text not null)""",
    "create index if not exists ix_team_notifications_user on team_notifications (user_id, is_read, created_at)",
]


class TeamError(Exception):
    def __init__(self, code: str, status: int = 400) -> None:
        super().__init__(code)
        self.code = code
        self.status = status


NOT_FOUND = lambda: TeamError("not_found", 404)  # noqa: E731
FORBIDDEN = lambda: TeamError("forbidden", 403)  # noqa: E731


def _db():
    return database("teams", SCHEMA)


def _id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:16]}"


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _clip(value: Any, limit: int) -> str | None:
    if value is None:
        return None
    text = " ".join(str(value).split())[:limit]
    return text or None


def _require(db, team_id: str, user_id: str, minimum: str = "viewer") -> str:  # noqa: ANN001
    row = db.one("select role from team_members where team_id = ? and user_id = ?", (team_id, user_id))
    if not row:
        raise NOT_FOUND()
    if RANK[row["role"]] < RANK[minimum]:
        raise FORBIDDEN()
    return row["role"]


def _log(db, team_id: str, actor: str, action: str, summary: str, target_type: str | None = None, target_id: str | None = None) -> None:  # noqa: ANN001
    db.run("insert into team_activity (id, team_id, actor_id, action, target_type, target_id, summary, created_at) values (?,?,?,?,?,?,?,?)", (_id("act"), team_id, actor, action, target_type, target_id, summary[:300], now_iso()))


def _notify(db, user_ids: list[str], team_id: str, kind: str, payload: dict[str, Any], *, skip: str | None = None) -> None:  # noqa: ANN001
    for user_id in dict.fromkeys(user_ids):
        if user_id and user_id != skip:
            db.run("insert into team_notifications (id, user_id, team_id, kind, payload, is_read, created_at) values (?,?,?,?,?,0,?)", (_id("ntf"), user_id, team_id, kind, json.dumps(payload, ensure_ascii=False), now_iso()))


# ------------------------------------------------------------------------------------------------- lookups used by billing


def teams_for_member(user_id: str) -> list[dict[str, Any]]:
    with _db() as db:
        return db.all("select t.id, t.owner_id, m.role from teams t join team_members m on m.team_id = t.id where m.user_id = ?", (user_id,))


def role_of(team_id: str, user_id: str) -> str | None:
    with _db() as db:
        row = db.one("select role from team_members where team_id = ? and user_id = ?", (team_id, user_id))
    return row["role"] if row else None


def member_count(team_id: str) -> int:
    with _db() as db:
        return int(db.scalar("select count(*) from team_members where team_id = ?", (team_id,)) or 0)


# ------------------------------------------------------------------------------------------------- teams + members


def create_team(user_id: str, *, name: str, description: str | None, display_name: str) -> dict[str, Any]:
    name = _clip(name, 120)
    if not name:
        raise TeamError("name_required")
    with _db() as db:
        if int(db.scalar("select count(*) from team_members where user_id = ?", (user_id,)) or 0) >= MAX_TEAMS_PER_USER:
            raise TeamError("team_limit", 409)
        team_id, stamp = _id("team"), now_iso()
        db.run("insert into teams (id, name, description, owner_id, created_at, updated_at) values (?,?,?,?,?,?)", (team_id, name, _clip(description, 500), user_id, stamp, stamp))
        db.run("insert into team_members (team_id, user_id, role, display_name, joined_at) values (?,?,?,?,?)", (team_id, user_id, "owner", _clip(display_name, 80) or "Owner", stamp))
        _log(db, team_id, user_id, "team.created", name)
    return team_detail(user_id, team_id)


def list_teams(user_id: str) -> list[dict[str, Any]]:
    with _db() as db:
        rows = db.all(
            "select t.*, m.role, (select count(*) from team_members x where x.team_id = t.id) as member_count,"
            " (select count(*) from team_projects p where p.team_id = t.id) as project_count"
            " from teams t join team_members m on m.team_id = t.id where m.user_id = ? order by t.updated_at desc",
            (user_id,),
        )
        unread = {row["team_id"]: row["n"] for row in db.all("select team_id, count(*) as n from team_notifications where user_id = ? and is_read = 0 group by team_id", (user_id,))}
    return [{**row, "unread": unread.get(row["id"], 0)} for row in rows]


def team_detail(user_id: str, team_id: str) -> dict[str, Any]:
    with _db() as db:
        role = _require(db, team_id, user_id)
        team = db.one("select * from teams where id = ?", (team_id,))
        members = db.all("select user_id, role, display_name, joined_at from team_members where team_id = ? order by joined_at", (team_id,))
        counts = {
            "projects": db.scalar("select count(*) from team_projects where team_id = ?", (team_id,)),
            "papers": db.scalar("select count(*) from team_project_papers where team_id = ?", (team_id,)),
            "pending_reviews": db.scalar("select count(*) from team_reviews where team_id = ? and status = 'pending'", (team_id,)),
        }
    members.sort(key=lambda member: (-RANK[member["role"]], member["joined_at"]))
    return {**team, "my_role": role, "my_user_id": user_id, "members": members, "counts": counts}


def update_team(user_id: str, team_id: str, *, name: str | None, description: str | None) -> dict[str, Any]:
    with _db() as db:
        _require(db, team_id, user_id, "admin")
        if name is not None:
            if not _clip(name, 120):
                raise TeamError("name_required")
            db.run("update teams set name = ?, updated_at = ? where id = ?", (_clip(name, 120), now_iso(), team_id))
        if description is not None:
            db.run("update teams set description = ?, updated_at = ? where id = ?", (_clip(description, 500), now_iso(), team_id))
        _log(db, team_id, user_id, "team.updated", _clip(name, 120) or "settings")
    return team_detail(user_id, team_id)


def delete_team(user_id: str, team_id: str) -> None:
    with _db() as db:
        _require(db, team_id, user_id, "owner")
        for table in ("team_members", "team_invites", "team_projects", "team_project_papers", "team_comments", "team_reviews", "team_activity", "team_notifications"):
            db.run(f"delete from {table} where team_id = ?", (team_id,))
        db.run("delete from teams where id = ?", (team_id,))


def update_member(user_id: str, team_id: str, member_id: str, *, role: str | None, display_name: str | None) -> dict[str, Any]:
    with _db() as db:
        my_role = _require(db, team_id, user_id, "viewer")
        target = db.one("select role from team_members where team_id = ? and user_id = ?", (team_id, member_id))
        if not target:
            raise NOT_FOUND()
        if display_name is not None:
            if member_id != user_id and RANK[my_role] < RANK["admin"]:
                raise FORBIDDEN()
            db.run("update team_members set display_name = ? where team_id = ? and user_id = ?", (_clip(display_name, 80) or "Member", team_id, member_id))
        if role is not None:
            if role not in ROLES or role == "owner":
                raise TeamError("invalid_role")
            if RANK[my_role] < RANK["admin"] or target["role"] == "owner" or (target["role"] == "admin" and my_role != "owner"):
                raise FORBIDDEN()
            db.run("update team_members set role = ? where team_id = ? and user_id = ?", (role, team_id, member_id))
            _log(db, team_id, user_id, "member.role", f"{member_id} → {role}", "member", member_id)
            _notify(db, [member_id], team_id, "role_changed", {"role": role}, skip=user_id)
    return team_detail(user_id, team_id)


def remove_member(user_id: str, team_id: str, member_id: str) -> None:
    with _db() as db:
        my_role = _require(db, team_id, user_id)
        target = db.one("select role from team_members where team_id = ? and user_id = ?", (team_id, member_id))
        if not target:
            raise NOT_FOUND()
        if target["role"] == "owner":
            raise TeamError("owner_cannot_leave", 409)
        if member_id != user_id and (RANK[my_role] < RANK["admin"] or (target["role"] == "admin" and my_role != "owner")):
            raise FORBIDDEN()
        db.run("delete from team_members where team_id = ? and user_id = ?", (team_id, member_id))
        db.run("update team_project_papers set assignee_id = null where team_id = ? and assignee_id = ?", (team_id, member_id))
        _log(db, team_id, user_id, "member.left" if member_id == user_id else "member.removed", member_id, "member", member_id)


def transfer_ownership(user_id: str, team_id: str, new_owner: str) -> dict[str, Any]:
    with _db() as db:
        _require(db, team_id, user_id, "owner")
        if not db.one("select 1 from team_members where team_id = ? and user_id = ?", (team_id, new_owner)):
            raise NOT_FOUND()
        db.run("update team_members set role = 'admin' where team_id = ? and user_id = ?", (team_id, user_id))
        db.run("update team_members set role = 'owner' where team_id = ? and user_id = ?", (team_id, new_owner))
        db.run("update teams set owner_id = ?, updated_at = ? where id = ?", (new_owner, now_iso(), team_id))
        _log(db, team_id, user_id, "team.transferred", new_owner, "member", new_owner)
    return team_detail(user_id, team_id)


# ------------------------------------------------------------------------------------------------- invites


def create_invite(user_id: str, team_id: str, *, role: str, email: str | None, days: int, max_uses: int) -> dict[str, Any]:
    if role not in ROLES or role == "owner":
        raise TeamError("invalid_role")
    with _db() as db:
        my_role = _require(db, team_id, user_id, "admin")
        if role == "admin" and my_role != "owner":
            raise FORBIDDEN()
        if int(db.scalar("select count(*) from team_members where team_id = ?", (team_id,)) or 0) >= MAX_MEMBERS:
            raise TeamError("member_limit", 409)
        token = secrets.token_urlsafe(24)
        invite = {
            "id": _id("inv"), "team_id": team_id, "token_hash": _hash(token), "role": role, "email": (email or "").strip().lower() or None,
            "created_by": user_id, "created_at": now_iso(), "expires_at": (datetime.now(UTC) + timedelta(days=max(1, min(days, 30)))).isoformat(),
            "max_uses": max(1, min(max_uses, 50)), "uses": 0, "revoked": 0,
        }
        db.run(f"insert into team_invites ({','.join(invite)}) values ({','.join('?' for _ in invite)})", tuple(invite.values()))
        _log(db, team_id, user_id, "invite.created", role, "invite", invite["id"])
    public = {key: value for key, value in invite.items() if key != "token_hash"}
    return {**public, "token": token}


def list_invites(user_id: str, team_id: str) -> list[dict[str, Any]]:
    with _db() as db:
        _require(db, team_id, user_id, "admin")
        rows = db.all("select id, role, email, created_by, created_at, expires_at, max_uses, uses, revoked from team_invites where team_id = ? order by created_at desc", (team_id,))
    now = datetime.now(UTC).isoformat()
    return [{**row, "active": not row["revoked"] and row["uses"] < row["max_uses"] and row["expires_at"] > now} for row in rows]


def revoke_invite(user_id: str, team_id: str, invite_id: str) -> None:
    with _db() as db:
        _require(db, team_id, user_id, "admin")
        if not db.run("update team_invites set revoked = 1 where id = ? and team_id = ?", (invite_id, team_id)):
            raise NOT_FOUND()


def _valid_invite(db, token: str) -> dict[str, Any]:  # noqa: ANN001
    invite = db.one("select * from team_invites where token_hash = ?", (_hash(token),))
    if not invite or invite["revoked"]:
        raise TeamError("invite_invalid", 404)
    if invite["expires_at"] < datetime.now(UTC).isoformat():
        raise TeamError("invite_expired", 410)
    if invite["uses"] >= invite["max_uses"]:
        raise TeamError("invite_used", 410)
    return invite


def preview_invite(token: str) -> dict[str, Any]:
    with _db() as db:
        invite = _valid_invite(db, token)
        team = db.one("select id, name, description from teams where id = ?", (invite["team_id"],))
        members = db.scalar("select count(*) from team_members where team_id = ?", (invite["team_id"],))
    return {"team": team, "role": invite["role"], "members": members, "expires_at": invite["expires_at"]}


def accept_invite(user_id: str, token: str, *, display_name: str) -> dict[str, Any]:
    with _db() as db:
        invite = _valid_invite(db, token)
        team_id = invite["team_id"]
        if db.one("select 1 from team_members where team_id = ? and user_id = ?", (team_id, user_id)):
            return {"team_id": team_id, "already_member": True}
        db.run("insert into team_members (team_id, user_id, role, display_name, joined_at) values (?,?,?,?,?)", (team_id, user_id, invite["role"], _clip(display_name, 80) or "Member", now_iso()))
        db.run("update team_invites set uses = uses + 1 where id = ?", (invite["id"],))
        _log(db, team_id, user_id, "member.joined", _clip(display_name, 80) or user_id, "member", user_id)
        admins = [row["user_id"] for row in db.all("select user_id from team_members where team_id = ? and role in ('owner','admin')", (team_id,))]
        _notify(db, admins, team_id, "member_joined", {"name": _clip(display_name, 80) or "Member"}, skip=user_id)
    return {"team_id": team_id, "already_member": False}


# ------------------------------------------------------------------------------------------------- shared projects


def create_project(user_id: str, team_id: str, *, name: str, description: str | None) -> dict[str, Any]:
    if not _clip(name, 160):
        raise TeamError("name_required")
    with _db() as db:
        _require(db, team_id, user_id, "admin")
        project_id, stamp = _id("tpj"), now_iso()
        db.run("insert into team_projects (id, team_id, name, description, created_by, created_at, updated_at) values (?,?,?,?,?,?,?)", (project_id, team_id, _clip(name, 160), _clip(description, 1000), user_id, stamp, stamp))
        _log(db, team_id, user_id, "project.created", _clip(name, 160), "project", project_id)
    return project_detail(user_id, team_id, project_id)


def list_projects(user_id: str, team_id: str) -> list[dict[str, Any]]:
    with _db() as db:
        _require(db, team_id, user_id)
        return db.all(
            "select p.*, (select count(*) from team_project_papers x where x.project_id = p.id) as paper_count,"
            " (select count(*) from team_project_papers x where x.project_id = p.id and x.status = 'done') as done_count,"
            " (select count(*) from team_comments c where c.target_type = 'project' and c.target_id = p.id and c.deleted = 0) as comment_count"
            " from team_projects p where p.team_id = ? order by p.updated_at desc",
            (team_id,),
        )


def _project(db, team_id: str, project_id: str) -> dict[str, Any]:  # noqa: ANN001
    project = db.one("select * from team_projects where id = ? and team_id = ?", (project_id, team_id))
    if not project:
        raise NOT_FOUND()
    return project


def project_detail(user_id: str, team_id: str, project_id: str) -> dict[str, Any]:
    with _db() as db:
        _require(db, team_id, user_id)
        project = _project(db, team_id, project_id)
        papers = db.all("select * from team_project_papers where project_id = ? order by added_at desc", (project_id,))
        counts = {row["target_id"]: row["n"] for row in db.all("select target_id, count(*) as n from team_comments where team_id = ? and target_type = 'paper' and deleted = 0 group by target_id", (team_id,))}
    for paper in papers:
        paper["authors"] = json.loads(paper["authors"] or "[]")
        paper["comment_count"] = counts.get(paper["id"], 0)
    return {**project, "papers": papers}


def update_project(user_id: str, team_id: str, project_id: str, *, name: str | None, description: str | None) -> dict[str, Any]:
    with _db() as db:
        _require(db, team_id, user_id, "admin")
        _project(db, team_id, project_id)
        if name is not None and _clip(name, 160):
            db.run("update team_projects set name = ?, updated_at = ? where id = ?", (_clip(name, 160), now_iso(), project_id))
        if description is not None:
            db.run("update team_projects set description = ?, updated_at = ? where id = ?", (_clip(description, 1000), now_iso(), project_id))
    return project_detail(user_id, team_id, project_id)


def delete_project(user_id: str, team_id: str, project_id: str) -> None:
    with _db() as db:
        _require(db, team_id, user_id, "admin")
        project = _project(db, team_id, project_id)
        paper_ids = [row["id"] for row in db.all("select id from team_project_papers where project_id = ?", (project_id,))]
        for paper_id in paper_ids:
            db.run("delete from team_comments where team_id = ? and target_type = 'paper' and target_id = ?", (team_id, paper_id))
        db.run("delete from team_comments where team_id = ? and target_type = 'project' and target_id = ?", (team_id, project_id))
        db.run("delete from team_project_papers where project_id = ?", (project_id,))
        db.run("delete from team_projects where id = ?", (project_id,))
        _log(db, team_id, user_id, "project.deleted", project["name"], "project", project_id)


def _paper_key(paper: dict[str, Any]) -> str:
    doi = (paper.get("doi") or "").strip().lower()
    if doi:
        return f"doi:{doi}"
    title = re.sub(r"[^\w]+", " ", (paper.get("title") or "").lower()).strip()
    return f"title:{title}:{paper.get('year') or ''}"


def add_papers(user_id: str, team_id: str, project_id: str, papers: list[dict[str, Any]]) -> dict[str, Any]:
    added = skipped = 0
    with _db() as db:
        _require(db, team_id, user_id, "member")
        project = _project(db, team_id, project_id)
        for paper in papers[:200]:
            title = _clip(paper.get("title"), 1000)
            if not title:
                continue
            key = _paper_key(paper)
            if db.one("select 1 from team_project_papers where project_id = ? and paper_key = ?", (project_id, key)):
                skipped += 1
                continue
            db.run(
                "insert into team_project_papers (id, project_id, team_id, paper_key, title, authors, year, venue, doi, url, abstract, status, assignee_id, added_by, added_at) values (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (_id("tpp"), project_id, team_id, key, title, json.dumps([_clip(a, 200) for a in (paper.get("authors") or [])[:50] if _clip(a, 200)], ensure_ascii=False),
                 paper.get("year") if isinstance(paper.get("year"), int) else None, _clip(paper.get("venue"), 300), _clip(paper.get("doi"), 200),
                 _clip(paper.get("url"), 1000), (paper.get("abstract") or "")[:8000] or None, "to_read", None, user_id, now_iso()),
            )
            added += 1
        db.run("update team_projects set updated_at = ? where id = ?", (now_iso(), project_id))
        if added:
            _log(db, team_id, user_id, "papers.added", f"{added} → {project['name']}", "project", project_id)
    return {"added": added, "skipped": skipped, "project": project_detail(user_id, team_id, project_id)}


def update_paper(user_id: str, team_id: str, project_id: str, paper_id: str, *, status: str | None, assignee_id: str | None, clear_assignee: bool) -> dict[str, Any]:
    with _db() as db:
        _require(db, team_id, user_id, "member")
        paper = db.one("select * from team_project_papers where id = ? and project_id = ? and team_id = ?", (paper_id, project_id, team_id))
        if not paper:
            raise NOT_FOUND()
        if status is not None:
            if status not in PAPER_STATUSES:
                raise TeamError("invalid_status")
            db.run("update team_project_papers set status = ? where id = ?", (status, paper_id))
        if clear_assignee:
            db.run("update team_project_papers set assignee_id = null where id = ?", (paper_id,))
        elif assignee_id is not None:
            if not db.one("select 1 from team_members where team_id = ? and user_id = ?", (team_id, assignee_id)):
                raise TeamError("not_a_member")
            db.run("update team_project_papers set assignee_id = ? where id = ?", (assignee_id, paper_id))
            _notify(db, [assignee_id], team_id, "paper_assigned", {"title": paper["title"][:200], "project_id": project_id}, skip=user_id)
    return project_detail(user_id, team_id, project_id)


def remove_paper(user_id: str, team_id: str, project_id: str, paper_id: str) -> None:
    with _db() as db:
        _require(db, team_id, user_id, "member")
        if not db.run("delete from team_project_papers where id = ? and project_id = ? and team_id = ?", (paper_id, project_id, team_id)):
            raise NOT_FOUND()
        db.run("delete from team_comments where team_id = ? and target_type = 'paper' and target_id = ?", (team_id, paper_id))


# ------------------------------------------------------------------------------------------------- comments + mentions

_MENTION = re.compile(r"@([\w.\-]+(?: [\w.\-]+)?)", re.UNICODE)


def _target_exists(db, team_id: str, target_type: str, target_id: str) -> None:  # noqa: ANN001
    table = {"project": "team_projects", "paper": "team_project_papers", "review": "team_reviews"}.get(target_type)
    if not table or not db.one(f"select 1 from {table} where id = ? and team_id = ?", (target_id, team_id)):
        raise NOT_FOUND()


def _mentions(db, team_id: str, body: str) -> list[str]:  # noqa: ANN001
    members = db.all("select user_id, display_name from team_members where team_id = ?", (team_id,))
    names = {member["display_name"].lower(): member["user_id"] for member in members}
    found = []
    for match in _MENTION.finditer(body):
        candidate = match.group(1).lower()
        for name in (candidate, candidate.split(" ")[0]):
            if name in names:
                found.append(names[name])
                break
    return list(dict.fromkeys(found))


def list_comments(user_id: str, team_id: str, target_type: str, target_id: str) -> list[dict[str, Any]]:
    with _db() as db:
        _require(db, team_id, user_id)
        _target_exists(db, team_id, target_type, target_id)
        rows = db.all(
            "select c.*, m.display_name as author_name from team_comments c left join team_members m on m.team_id = c.team_id and m.user_id = c.author_id"
            " where c.team_id = ? and c.target_type = ? and c.target_id = ? order by c.created_at",
            (team_id, target_type, target_id),
        )
    for row in rows:
        row["mentions"] = json.loads(row["mentions"] or "[]")
        if row["deleted"]:
            row["body"] = ""
    return rows


def add_comment(user_id: str, team_id: str, *, target_type: str, target_id: str, body: str, parent_id: str | None) -> dict[str, Any]:
    text = (body or "").strip()[:5000]
    if not text:
        raise TeamError("empty_comment")
    with _db() as db:
        _require(db, team_id, user_id, "member")
        _target_exists(db, team_id, target_type, target_id)
        if parent_id and not db.one("select 1 from team_comments where id = ? and team_id = ? and target_id = ?", (parent_id, team_id, target_id)):
            raise NOT_FOUND()
        mentioned = _mentions(db, team_id, text)
        comment_id = _id("cmt")
        db.run("insert into team_comments (id, team_id, target_type, target_id, author_id, body, mentions, parent_id, created_at, deleted) values (?,?,?,?,?,?,?,?,?,0)", (comment_id, team_id, target_type, target_id, user_id, text, json.dumps(mentioned), parent_id, now_iso()))
        author = db.one("select display_name from team_members where team_id = ? and user_id = ?", (team_id, user_id))["display_name"]
        _notify(db, mentioned, team_id, "mention", {"by": author, "target_type": target_type, "target_id": target_id, "excerpt": text[:160]}, skip=user_id)
        if parent_id:
            parent_author = db.one("select author_id from team_comments where id = ?", (parent_id,))["author_id"]
            _notify(db, [parent_author], team_id, "reply", {"by": author, "target_type": target_type, "target_id": target_id, "excerpt": text[:160]}, skip=user_id)
        _log(db, team_id, user_id, "comment.added", text[:120], target_type, target_id)
    return next(comment for comment in list_comments(user_id, team_id, target_type, target_id) if comment["id"] == comment_id)


def edit_comment(user_id: str, team_id: str, comment_id: str, *, body: str | None, delete: bool) -> None:
    with _db() as db:
        role = _require(db, team_id, user_id)
        comment = db.one("select * from team_comments where id = ? and team_id = ?", (comment_id, team_id))
        if not comment or comment["deleted"]:
            raise NOT_FOUND()
        if delete:
            if comment["author_id"] != user_id and RANK[role] < RANK["admin"]:
                raise FORBIDDEN()
            db.run("update team_comments set deleted = 1, edited_at = ? where id = ?", (now_iso(), comment_id))
            return
        if comment["author_id"] != user_id:
            raise FORBIDDEN()
        text = (body or "").strip()[:5000]
        if not text:
            raise TeamError("empty_comment")
        db.run("update team_comments set body = ?, mentions = ?, edited_at = ? where id = ?", (text, json.dumps(_mentions(db, team_id, text)), now_iso(), comment_id))


# ------------------------------------------------------------------------------------------------- supervisor reviews


def request_review(user_id: str, team_id: str, *, document_id: str, title: str, snapshot: str, reviewer_id: str | None) -> dict[str, Any]:
    with _db() as db:
        _require(db, team_id, user_id, "member")
        if reviewer_id:
            reviewer_role = db.one("select role from team_members where team_id = ? and user_id = ?", (team_id, reviewer_id))
            if not reviewer_role or RANK[reviewer_role["role"]] < RANK["supervisor"]:
                raise TeamError("reviewer_not_supervisor")
        previous = db.one("select max(round) as r from team_reviews where team_id = ? and document_id = ? and requested_by = ?", (team_id, document_id, user_id))
        review_id = _id("rev")
        db.run(
            "insert into team_reviews (id, team_id, document_id, title, snapshot, requested_by, reviewer_id, status, created_at, round) values (?,?,?,?,?,?,?,?,?,?)",
            (review_id, team_id, document_id, _clip(title, 300) or "Untitled", snapshot[:200000], user_id, reviewer_id, "pending", now_iso(), int((previous or {}).get("r") or 0) + 1),
        )
        supervisors = [reviewer_id] if reviewer_id else [row["user_id"] for row in db.all("select user_id from team_members where team_id = ? and role in ('owner','admin','supervisor')", (team_id,))]
        requester = db.one("select display_name from team_members where team_id = ? and user_id = ?", (team_id, user_id))["display_name"]
        _notify(db, supervisors, team_id, "review_requested", {"review_id": review_id, "title": _clip(title, 200), "by": requester}, skip=user_id)
        _log(db, team_id, user_id, "review.requested", _clip(title, 200) or "", "review", review_id)
    return review_detail(user_id, team_id, review_id)


def list_reviews(user_id: str, team_id: str) -> list[dict[str, Any]]:
    with _db() as db:
        _require(db, team_id, user_id)
        return db.all(
            "select r.id, r.document_id, r.title, r.requested_by, r.reviewer_id, r.status, r.created_at, r.decided_at, r.round,"
            " m.display_name as requester_name, (select count(*) from team_comments c where c.target_type = 'review' and c.target_id = r.id and c.deleted = 0) as comment_count"
            " from team_reviews r left join team_members m on m.team_id = r.team_id and m.user_id = r.requested_by where r.team_id = ? order by r.created_at desc",
            (team_id,),
        )


def review_detail(user_id: str, team_id: str, review_id: str) -> dict[str, Any]:
    with _db() as db:
        role = _require(db, team_id, user_id)
        review = db.one("select * from team_reviews where id = ? and team_id = ?", (review_id, team_id))
        if not review:
            raise NOT_FOUND()
    can_decide = RANK[role] >= RANK["supervisor"] and review["requested_by"] != user_id and review["status"] == "pending" and (not review["reviewer_id"] or review["reviewer_id"] == user_id or RANK[role] >= RANK["admin"])
    return {**review, "can_decide": can_decide}


def decide_review(user_id: str, team_id: str, review_id: str, *, status: str, note: str | None) -> dict[str, Any]:
    if status not in ("approved", "changes_requested"):
        raise TeamError("invalid_status")
    detail = review_detail(user_id, team_id, review_id)
    if not detail["can_decide"]:
        raise FORBIDDEN()
    with _db() as db:
        db.run("update team_reviews set status = ?, decision_note = ?, decided_at = ?, decided_by = ? where id = ?", (status, _clip(note, 4000), now_iso(), user_id, review_id))
        decider = db.one("select display_name from team_members where team_id = ? and user_id = ?", (team_id, user_id))["display_name"]
        _notify(db, [detail["requested_by"]], team_id, "review_decided", {"review_id": review_id, "status": status, "title": detail["title"][:200], "by": decider}, skip=user_id)
        _log(db, team_id, user_id, f"review.{status}", detail["title"][:200], "review", review_id)
    return review_detail(user_id, team_id, review_id)


# ------------------------------------------------------------------------------------------------- activity + notifications


def activity(user_id: str, team_id: str, limit: int = 100) -> list[dict[str, Any]]:
    with _db() as db:
        _require(db, team_id, user_id)
        return db.all(
            "select a.*, m.display_name as actor_name from team_activity a left join team_members m on m.team_id = a.team_id and m.user_id = a.actor_id"
            " where a.team_id = ? order by a.created_at desc limit ?",
            (team_id, max(1, min(limit, 500))),
        )


def notifications(user_id: str, *, unread_only: bool = False) -> list[dict[str, Any]]:
    with _db() as db:
        rows = db.all(
            "select n.*, t.name as team_name from team_notifications n left join teams t on t.id = n.team_id where n.user_id = ?"
            + (" and n.is_read = 0" if unread_only else "") + " order by n.created_at desc limit 100",
            (user_id,),
        )
    for row in rows:
        row["payload"] = json.loads(row["payload"] or "{}")
        row["is_read"] = bool(row["is_read"])
    return rows


def mark_read(user_id: str, ids: list[str] | None) -> int:
    with _db() as db:
        if ids:
            return sum(db.run("update team_notifications set is_read = 1 where user_id = ? and id = ?", (user_id, notification_id)) for notification_id in ids[:200])
        return db.run("update team_notifications set is_read = 1 where user_id = ? and is_read = 0", (user_id,))
