"""Library persistence: saved papers, projects, collections, notes, ideas and tasks — always scoped to one owner.

Works on the same database as the rest of the API (``settings.database_url``): SQLite in development, Postgres in
production. Tables are created on first use, so no separate migration step is needed. Every query filters by owner;
an id that belongs to someone else behaves exactly like an id that does not exist.
"""

from __future__ import annotations

import json
import os
import re
import sqlite3
import unicodedata
from contextlib import contextmanager
from datetime import UTC, datetime
from typing import Any, Iterable
from uuid import uuid4

from app.core.config import settings

STATUSES = ("to_read", "reading", "read")
LIST_KINDS = ("project", "collection")
NOTE_KINDS = ("note", "idea")
IDEA_STATUSES = ("new", "exploring", "parked", "done")
PRIORITIES = ("normal", "high")
MAX_ITEMS_PER_OWNER = int(os.getenv("LIBRARY_MAX_ITEMS", "10000"))
MAX_TAGS = 20
MAX_TAG_LENGTH = 40

_SCHEMA = [
    """create table if not exists library_items (
        id text primary key,
        owner_id text not null,
        paper_key text not null,
        title text not null,
        authors text not null default '[]',
        year integer,
        venue text,
        doi text,
        arxiv_id text,
        url text,
        pdf_url text,
        abstract text,
        reader_doc_id text,
        source text not null default 'manual',
        status text not null default 'to_read',
        important integer not null default 0,
        read_later integer not null default 0,
        tags text not null default '[]',
        added_at text not null,
        updated_at text not null,
        opened_at text,
        unique (owner_id, paper_key)
    )""",
    "create index if not exists library_items_owner_idx on library_items(owner_id, added_at)",
    """create table if not exists library_lists (
        id text primary key,
        owner_id text not null,
        kind text not null,
        name text not null,
        description text,
        created_at text not null,
        updated_at text not null
    )""",
    "create index if not exists library_lists_owner_idx on library_lists(owner_id, kind)",
    """create table if not exists library_list_items (
        list_id text not null,
        item_id text not null,
        added_at text not null,
        primary key (list_id, item_id)
    )""",
    """create table if not exists library_notes (
        id text primary key,
        owner_id text not null,
        kind text not null,
        title text,
        body text not null default '',
        quote text,
        page integer,
        item_id text,
        project_id text,
        status text,
        created_at text not null,
        updated_at text not null
    )""",
    "create index if not exists library_notes_owner_idx on library_notes(owner_id, kind)",
    """create table if not exists library_tasks (
        id text primary key,
        owner_id text not null,
        title text not null,
        due_date text,
        done integer not null default 0,
        priority text not null default 'normal',
        project_id text,
        item_id text,
        created_at text not null,
        updated_at text not null,
        completed_at text
    )""",
    "create index if not exists library_tasks_owner_idx on library_tasks(owner_id, done)",
]

ITEM_COLUMNS = ("id", "paper_key", "title", "authors", "year", "venue", "doi", "arxiv_id", "url", "pdf_url", "abstract", "reader_doc_id", "source", "status", "important", "read_later", "tags", "added_at", "updated_at", "opened_at")
NOTE_COLUMNS = ("id", "kind", "title", "body", "quote", "page", "item_id", "project_id", "status", "created_at", "updated_at")
TASK_COLUMNS = ("id", "title", "due_date", "done", "priority", "project_id", "item_id", "created_at", "updated_at", "completed_at")
LIST_COLUMNS = ("id", "kind", "name", "description", "created_at", "updated_at")


_READY: set[str] = set()  # databases whose tables were already created in this process


class LibraryNotFound(LookupError):
    """The id does not exist for this owner."""


class LibraryLimit(ValueError):
    """The owner reached the item limit."""


def now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def normalize_doi(value: str | None) -> str | None:
    if not value:
        return None
    text = value.strip()
    text = re.sub(r"^(?:https?://(?:dx\.)?doi\.org/|doi:\s*)", "", text, flags=re.IGNORECASE)
    match = re.search(r"10\.\d{4,9}/\S+", text)
    return match.group(0).rstrip(".,;)").lower() if match else None


def normalize_arxiv(value: str | None) -> str | None:
    if not value:
        return None
    match = re.search(r"(?:arxiv\.org/(?:abs|pdf)/|arxiv:\s*)?(\d{4}\.\d{4,5}|[a-z\-]+(?:\.[A-Z]{2})?/\d{7})(?:v\d+)?", value.strip(), flags=re.IGNORECASE)
    return match.group(1).lower() if match else None


def normalize_title(title: str) -> str:
    text = unicodedata.normalize("NFKD", title or "").casefold()
    return re.sub(r"[^\w]+", "", text, flags=re.UNICODE)[:200]


def paper_key(*, doi: str | None = None, arxiv_id: str | None = None, title: str = "", year: int | None = None) -> str:
    """One stable identity per paper, so the same work saved from Search, Reader or an import is stored once."""
    if normalize_doi(doi):
        return f"doi:{normalize_doi(doi)}"
    if normalize_arxiv(arxiv_id):
        return f"arxiv:{normalize_arxiv(arxiv_id)}"
    return f"title:{normalize_title(title)}:{year or ''}"


def clean_tags(tags: Iterable[str] | None) -> list[str]:
    result: list[str] = []
    for tag in tags or []:
        value = re.sub(r"\s+", " ", str(tag)).strip().lstrip("#")[:MAX_TAG_LENGTH]
        if value and value.casefold() not in {item.casefold() for item in result}:
            result.append(value)
    return result[:MAX_TAGS]


def clean_authors(authors: Iterable[Any] | None) -> list[str]:
    names: list[str] = []
    for author in authors or []:
        name = author.get("name") if isinstance(author, dict) else author
        name = re.sub(r"\s+", " ", str(name or "")).strip()
        if name and name.casefold() != "unknown":
            names.append(name[:200])
    return names[:100]


class LibraryStore:
    """All library data for all owners. Stateless: every call opens a short connection."""

    # ------------------------------------------------------------------ connection

    @staticmethod
    def _connect():
        url = settings.database_url
        if url.startswith("sqlite:///"):
            path = url.removeprefix("sqlite:///")
            if os.path.dirname(path):
                os.makedirs(os.path.dirname(path), exist_ok=True)
            return sqlite3.connect(path, timeout=10)
        import psycopg

        return psycopg.connect(url.replace("postgresql+psycopg://", "postgresql://", 1), connect_timeout=5)

    @contextmanager
    def _db(self):
        connection = self._connect()
        try:
            cursor = connection.cursor()
            if settings.database_url not in _READY:
                for statement in _SCHEMA:
                    cursor.execute(statement)
                connection.commit()
                _READY.add(settings.database_url)
            yield _Session(connection, cursor)
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    # ------------------------------------------------------------------ items

    def add_items(self, owner: str, papers: list[dict[str, Any]], *, source: str, list_id: str | None = None, tags: list[str] | None = None, read_later: bool = False) -> tuple[list[dict], list[str]]:
        """Save papers. Returns (items, ids_that_were_already_saved). Saving again never creates a duplicate."""
        stamp = now()
        saved: list[dict] = []
        existing_ids: list[str] = []
        extra_tags = clean_tags(tags)
        with self._db() as db:
            if list_id:
                self._own_list(db, owner, list_id)
            count = db.one("select count(*) from library_items where owner_id=?", (owner,))[0]
            for paper in papers:
                title = re.sub(r"\s+", " ", str(paper.get("title") or "")).strip()[:600]
                if not title:
                    continue
                doi = normalize_doi(paper.get("doi"))
                arxiv = normalize_arxiv(paper.get("arxiv_id") or (paper.get("url") if "arxiv.org" in str(paper.get("url") or "") else None))
                year = paper.get("year") if isinstance(paper.get("year"), int) else None
                key = paper_key(doi=doi, arxiv_id=arxiv, title=title, year=year)
                row = db.one("select id, tags, read_later, reader_doc_id, pdf_url, abstract from library_items where owner_id=? and paper_key=?", (owner, key))
                if row:
                    item_id = row[0]
                    existing_ids.append(item_id)
                    merged_tags = clean_tags([*json.loads(row[1] or "[]"), *extra_tags])
                    db.run(
                        "update library_items set tags=?, read_later=?, reader_doc_id=?, pdf_url=?, abstract=?, updated_at=? where id=?",
                        (json.dumps(merged_tags, ensure_ascii=False), 1 if (read_later or row[2]) else 0, row[3] or paper.get("reader_doc_id"), row[4] or paper.get("pdf_url"), row[5] or _clip(paper.get("abstract"), 6000), stamp, item_id),
                    )
                else:
                    if count >= MAX_ITEMS_PER_OWNER:
                        raise LibraryLimit("Library is full")
                    item_id = str(uuid4())
                    count += 1
                    db.run(
                        "insert into library_items (id, owner_id, paper_key, title, authors, year, venue, doi, arxiv_id, url, pdf_url, abstract, reader_doc_id, source, status, important, read_later, tags, added_at, updated_at) values (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                        (item_id, owner, key, title, json.dumps(clean_authors(paper.get("authors")), ensure_ascii=False), year, _clip(paper.get("venue"), 300), doi, arxiv,
                         _clip(paper.get("url"), 1000), _clip(paper.get("pdf_url"), 1000), _clip(paper.get("abstract"), 6000), _clip(paper.get("reader_doc_id"), 120),
                         source, "to_read", 0, 1 if read_later else 0, json.dumps(extra_tags, ensure_ascii=False), stamp, stamp),
                    )
                if list_id:
                    db.run(_upsert_link(db), (list_id, item_id, stamp))
                saved.append(self._item(db, owner, item_id))
        return saved, existing_ids

    def list_items(self, owner: str) -> list[dict]:
        with self._db() as db:
            rows = db.all(f"select {', '.join(ITEM_COLUMNS)} from library_items where owner_id=? order by added_at desc", (owner,))
            links = db.all("select l.list_id, l.item_id from library_list_items l join library_lists s on s.id = l.list_id where s.owner_id=?", (owner,))
        by_item: dict[str, list[str]] = {}
        for list_id, item_id in links:
            by_item.setdefault(item_id, []).append(list_id)
        return [_item_dict(row, by_item.get(row[0], [])) for row in rows]

    def get_item(self, owner: str, item_id: str) -> dict:
        with self._db() as db:
            return self._item(db, owner, item_id)

    def update_item(self, owner: str, item_id: str, changes: dict[str, Any]) -> dict:
        with self._db() as db:
            self._item(db, owner, item_id)
            fields, values = [], []
            if "status" in changes and changes["status"] in STATUSES:
                fields.append("status=?"); values.append(changes["status"])
            for flag in ("important", "read_later"):
                if flag in changes and changes[flag] is not None:
                    fields.append(f"{flag}=?"); values.append(1 if changes[flag] else 0)
            if changes.get("tags") is not None:
                fields.append("tags=?"); values.append(json.dumps(clean_tags(changes["tags"]), ensure_ascii=False))
            if changes.get("opened"):
                fields.append("opened_at=?"); values.append(now())
                if changes.get("status") is None:
                    fields.append("status=case when status='to_read' then 'reading' else status end")
            if changes.get("reader_doc_id"):
                fields.append("reader_doc_id=?"); values.append(_clip(changes["reader_doc_id"], 120))
            if fields:
                fields.append("updated_at=?"); values.append(now())
                db.run(f"update library_items set {', '.join(fields)} where id=? and owner_id=?", (*values, item_id, owner))
            return self._item(db, owner, item_id)

    def delete_items(self, owner: str, item_ids: list[str]) -> int:
        removed = 0
        with self._db() as db:
            for item_id in item_ids:
                if not db.one("select 1 from library_items where id=? and owner_id=?", (item_id, owner)):
                    continue
                db.run("delete from library_list_items where item_id=?", (item_id,))
                db.run("update library_notes set item_id=null where item_id=? and owner_id=?", (item_id, owner))
                db.run("update library_tasks set item_id=null where item_id=? and owner_id=?", (item_id, owner))
                db.run("delete from library_items where id=? and owner_id=?", (item_id, owner))
                removed += 1
        return removed

    def bulk(self, owner: str, item_ids: list[str], action: str, value: Any) -> int:
        owned = [item["id"] for item in self.list_items(owner) if item["id"] in set(item_ids)]
        if action == "delete":
            return self.delete_items(owner, owned)
        if action in {"add_to_list", "remove_from_list"}:
            with self._db() as db:
                self._own_list(db, owner, str(value))
                for item_id in owned:
                    if action == "add_to_list":
                        db.run(_upsert_link(db), (str(value), item_id, now()))
                    else:
                        db.run("delete from library_list_items where list_id=? and item_id=?", (str(value), item_id))
            return len(owned)
        for item_id in owned:
            if action == "set_status":
                self.update_item(owner, item_id, {"status": value})
            elif action in {"important", "read_later"}:
                self.update_item(owner, item_id, {action: bool(value)})
            elif action in {"add_tag", "remove_tag"}:
                current = self.get_item(owner, item_id)["tags"]
                tags = [*current, str(value)] if action == "add_tag" else [tag for tag in current if tag.casefold() != str(value).casefold()]
                self.update_item(owner, item_id, {"tags": tags})
        return len(owned)

    def lookup(self, owner: str, keys: list[str]) -> dict[str, str]:
        """Which of these paper keys are already saved (key → item id)."""
        wanted = {key for key in keys if key}
        if not wanted:
            return {}
        with self._db() as db:
            rows = db.all("select paper_key, id from library_items where owner_id=?", (owner,))
        return {key: item_id for key, item_id in rows if key in wanted}

    # ------------------------------------------------------------------ projects and collections

    def list_lists(self, owner: str, kind: str | None = None) -> list[dict]:
        with self._db() as db:
            query = f"select {', '.join(LIST_COLUMNS)} from library_lists where owner_id=?" + (" and kind=?" if kind else "") + " order by updated_at desc"
            rows = db.all(query, (owner, kind) if kind else (owner,))
            result = []
            for row in rows:
                record = dict(zip(LIST_COLUMNS, row))
                record["item_count"] = db.one("select count(*) from library_list_items where list_id=?", (record["id"],))[0]
                if record["kind"] == "project":
                    record["stats"] = self._project_stats(db, owner, record["id"])
                result.append(record)
        return result

    def create_list(self, owner: str, kind: str, name: str, description: str | None = None) -> dict:
        if kind not in LIST_KINDS:
            raise ValueError("kind")
        stamp = now()
        list_id = str(uuid4())
        with self._db() as db:
            db.run("insert into library_lists (id, owner_id, kind, name, description, created_at, updated_at) values (?,?,?,?,?,?,?)",
                   (list_id, owner, kind, name.strip()[:160], _clip(description, 2000), stamp, stamp))
        return self.get_list(owner, list_id)

    def get_list(self, owner: str, list_id: str) -> dict:
        with self._db() as db:
            row = self._own_list(db, owner, list_id)
            record = dict(zip(LIST_COLUMNS, row))
            record["item_ids"] = [item_id for (item_id,) in db.all("select item_id from library_list_items where list_id=? order by added_at desc", (list_id,))]
            record["item_count"] = len(record["item_ids"])
            if record["kind"] == "project":
                record["stats"] = self._project_stats(db, owner, list_id)
        return record

    def update_list(self, owner: str, list_id: str, name: str | None, description: str | None) -> dict:
        with self._db() as db:
            self._own_list(db, owner, list_id)
            if name is not None:
                db.run("update library_lists set name=?, updated_at=? where id=?", (name.strip()[:160], now(), list_id))
            if description is not None:
                db.run("update library_lists set description=?, updated_at=? where id=?", (_clip(description, 2000), now(), list_id))
        return self.get_list(owner, list_id)

    def delete_list(self, owner: str, list_id: str) -> None:
        """Deleting a project or collection never deletes the saved papers, notes or tasks in it."""
        with self._db() as db:
            self._own_list(db, owner, list_id)
            db.run("delete from library_list_items where list_id=?", (list_id,))
            db.run("update library_notes set project_id=null where project_id=? and owner_id=?", (list_id, owner))
            db.run("update library_tasks set project_id=null where project_id=? and owner_id=?", (list_id, owner))
            db.run("delete from library_lists where id=? and owner_id=?", (list_id, owner))

    def touch_list(self, owner: str, list_id: str) -> None:
        with self._db() as db:
            db.run("update library_lists set updated_at=? where id=? and owner_id=?", (now(), list_id, owner))

    # ------------------------------------------------------------------ notes and ideas

    def list_notes(self, owner: str, *, kind: str | None = None, project_id: str | None = None, item_id: str | None = None) -> list[dict]:
        clauses, values = ["owner_id=?"], [owner]
        for column, value in (("kind", kind), ("project_id", project_id), ("item_id", item_id)):
            if value:
                clauses.append(f"{column}=?"); values.append(value)
        with self._db() as db:
            rows = db.all(f"select {', '.join(NOTE_COLUMNS)} from library_notes where {' and '.join(clauses)} order by updated_at desc", tuple(values))
        return [dict(zip(NOTE_COLUMNS, row)) for row in rows]

    def create_note(self, owner: str, data: dict[str, Any]) -> dict:
        kind = data.get("kind") if data.get("kind") in NOTE_KINDS else "note"
        stamp = now()
        note_id = str(uuid4())
        with self._db() as db:
            item_id, project_id = self._own_links(db, owner, data.get("item_id"), data.get("project_id"))
            db.run("insert into library_notes (id, owner_id, kind, title, body, quote, page, item_id, project_id, status, created_at, updated_at) values (?,?,?,?,?,?,?,?,?,?,?,?)",
                   (note_id, owner, kind, _clip(data.get("title"), 300), _clip(data.get("body"), 20000) or "", _clip(data.get("quote"), 2000), _page(data.get("page")),
                    item_id, project_id, ("new" if kind == "idea" else None) if data.get("status") not in IDEA_STATUSES else data.get("status"), stamp, stamp))
            if project_id:
                db.run("update library_lists set updated_at=? where id=?", (stamp, project_id))
        return self._note(owner, note_id)

    def update_note(self, owner: str, note_id: str, data: dict[str, Any]) -> dict:
        current = self._note(owner, note_id)
        with self._db() as db:
            item_id, project_id = self._own_links(db, owner, data.get("item_id", current["item_id"]) or None, data.get("project_id", current["project_id"]) or None)
            status = data.get("status") if data.get("status") in IDEA_STATUSES else current["status"]
            db.run("update library_notes set title=?, body=?, quote=?, page=?, item_id=?, project_id=?, status=?, updated_at=? where id=? and owner_id=?",
                   (_clip(data.get("title", current["title"]), 300), _clip(data.get("body", current["body"]), 20000) or "", _clip(data.get("quote", current["quote"]), 2000),
                    _page(data.get("page", current["page"])), item_id, project_id, status, now(), note_id, owner))
        return self._note(owner, note_id)

    def delete_note(self, owner: str, note_id: str) -> None:
        self._note(owner, note_id)
        with self._db() as db:
            db.run("delete from library_notes where id=? and owner_id=?", (note_id, owner))

    # ------------------------------------------------------------------ tasks

    def list_tasks(self, owner: str, *, project_id: str | None = None) -> list[dict]:
        clauses, values = ["owner_id=?"], [owner]
        if project_id:
            clauses.append("project_id=?"); values.append(project_id)
        with self._db() as db:
            rows = db.all(f"select {', '.join(TASK_COLUMNS)} from library_tasks where {' and '.join(clauses)} order by done, coalesce(due_date, '9999'), created_at", tuple(values))
        return [_task_dict(row) for row in rows]

    def create_task(self, owner: str, data: dict[str, Any]) -> dict:
        stamp = now()
        task_id = str(uuid4())
        with self._db() as db:
            item_id, project_id = self._own_links(db, owner, data.get("item_id"), data.get("project_id"))
            db.run("insert into library_tasks (id, owner_id, title, due_date, done, priority, project_id, item_id, created_at, updated_at) values (?,?,?,?,?,?,?,?,?,?)",
                   (task_id, owner, str(data.get("title") or "").strip()[:300], _date(data.get("due_date")), 0, data.get("priority") if data.get("priority") in PRIORITIES else "normal", project_id, item_id, stamp, stamp))
        return self._task(owner, task_id)

    def update_task(self, owner: str, task_id: str, data: dict[str, Any]) -> dict:
        current = self._task(owner, task_id)
        with self._db() as db:
            item_id, project_id = self._own_links(db, owner, data.get("item_id", current["item_id"]) or None, data.get("project_id", current["project_id"]) or None)
            done = bool(data["done"]) if data.get("done") is not None else current["done"]
            completed = (current["completed_at"] or now()) if done else None
            title = str(data.get("title") or current["title"]).strip()[:300]
            due = _date(data["due_date"]) if "due_date" in data else current["due_date"]
            priority = data.get("priority") if data.get("priority") in PRIORITIES else current["priority"]
            db.run("update library_tasks set title=?, due_date=?, done=?, priority=?, project_id=?, item_id=?, completed_at=?, updated_at=? where id=? and owner_id=?",
                   (title, due, 1 if done else 0, priority, project_id, item_id, completed, now(), task_id, owner))
        return self._task(owner, task_id)

    def delete_task(self, owner: str, task_id: str) -> None:
        self._task(owner, task_id)
        with self._db() as db:
            db.run("delete from library_tasks where id=? and owner_id=?", (task_id, owner))

    # ------------------------------------------------------------------ overview

    def overview(self, owner: str, today: str | None = None) -> dict:
        items = self.list_items(owner)
        today = today or datetime.now(UTC).date().isoformat()
        with self._db() as db:
            notes = db.one("select count(*) from library_notes where owner_id=? and kind='note'", (owner,))[0]
            ideas = db.one("select count(*) from library_notes where owner_id=? and kind='idea' and coalesce(status,'new')<>'done'", (owner,))[0]
            open_tasks = db.one("select count(*) from library_tasks where owner_id=? and done=0", (owner,))[0]
            overdue = db.one("select count(*) from library_tasks where owner_id=? and done=0 and due_date is not null and due_date<?", (owner, today))[0]
            projects = db.one("select count(*) from library_lists where owner_id=? and kind='project'", (owner,))[0]
            collections = db.one("select count(*) from library_lists where owner_id=? and kind='collection'", (owner,))[0]
        tags: dict[str, int] = {}
        for item in items:
            for tag in item["tags"]:
                tags[tag] = tags.get(tag, 0) + 1
        return {
            "counts": {
                "saved": len(items),
                "to_read": sum(1 for item in items if item["status"] == "to_read"),
                "reading": sum(1 for item in items if item["status"] == "reading"),
                "read": sum(1 for item in items if item["status"] == "read"),
                "important": sum(1 for item in items if item["important"]),
                "read_later": sum(1 for item in items if item["read_later"]),
                "notes": notes,
                "ideas": ideas,
                "tasks_open": open_tasks,
                "tasks_overdue": overdue,
                "projects": projects,
                "collections": collections,
            },
            "tags": [{"tag": tag, "count": count} for tag, count in sorted(tags.items(), key=lambda pair: (-pair[1], pair[0].casefold()))],
        }

    # ------------------------------------------------------------------ helpers

    def _item(self, db: "_Session", owner: str, item_id: str) -> dict:
        row = db.one(f"select {', '.join(ITEM_COLUMNS)} from library_items where id=? and owner_id=?", (item_id, owner))
        if not row:
            raise LibraryNotFound(item_id)
        lists = [list_id for (list_id,) in db.all("select list_id from library_list_items where item_id=?", (item_id,))]
        return _item_dict(row, lists)

    def _note(self, owner: str, note_id: str) -> dict:
        with self._db() as db:
            row = db.one(f"select {', '.join(NOTE_COLUMNS)} from library_notes where id=? and owner_id=?", (note_id, owner))
        if not row:
            raise LibraryNotFound(note_id)
        return dict(zip(NOTE_COLUMNS, row))

    def _task(self, owner: str, task_id: str) -> dict:
        with self._db() as db:
            row = db.one(f"select {', '.join(TASK_COLUMNS)} from library_tasks where id=? and owner_id=?", (task_id, owner))
        if not row:
            raise LibraryNotFound(task_id)
        return _task_dict(row)

    @staticmethod
    def _own_list(db: "_Session", owner: str, list_id: str):
        row = db.one(f"select {', '.join(LIST_COLUMNS)} from library_lists where id=? and owner_id=?", (list_id, owner))
        if not row:
            raise LibraryNotFound(list_id)
        return row

    def _own_links(self, db: "_Session", owner: str, item_id: str | None, project_id: str | None) -> tuple[str | None, str | None]:
        if item_id and not db.one("select 1 from library_items where id=? and owner_id=?", (item_id, owner)):
            raise LibraryNotFound(item_id)
        if project_id:
            row = self._own_list(db, owner, project_id)
            if row[1] != "project":
                raise LibraryNotFound(project_id)
        return item_id or None, project_id or None

    @staticmethod
    def _project_stats(db: "_Session", owner: str, project_id: str) -> dict[str, int]:
        papers = db.all("select i.status, i.important from library_list_items l join library_items i on i.id = l.item_id where l.list_id=? and i.owner_id=?", (project_id, owner))
        return {
            "papers": len(papers),
            "to_read": sum(1 for status, _ in papers if status == "to_read"),
            "important": sum(1 for _, important in papers if important),
            "notes": db.one("select count(*) from library_notes where project_id=? and owner_id=? and kind='note'", (project_id, owner))[0],
            "ideas": db.one("select count(*) from library_notes where project_id=? and owner_id=? and kind='idea'", (project_id, owner))[0],
            "tasks_open": db.one("select count(*) from library_tasks where project_id=? and owner_id=? and done=0", (project_id, owner))[0],
        }


class _Session:
    def __init__(self, connection, cursor) -> None:
        self.connection = connection
        self.cursor = cursor
        self.sqlite = isinstance(connection, sqlite3.Connection)

    def _sql(self, sql: str) -> str:
        return sql if self.sqlite else sql.replace("?", "%s")

    def run(self, sql: str, values: tuple = ()) -> None:
        self.cursor.execute(self._sql(sql), values)

    def one(self, sql: str, values: tuple = ()):
        self.cursor.execute(self._sql(sql), values)
        return self.cursor.fetchone()

    def all(self, sql: str, values: tuple = ()):
        self.cursor.execute(self._sql(sql), values)
        return self.cursor.fetchall()


def _upsert_link(db: _Session) -> str:
    return "insert into library_list_items (list_id, item_id, added_at) values (?,?,?) on conflict (list_id, item_id) do nothing"


def _clip(value: Any, limit: int) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text[:limit] or None


def _page(value: Any) -> int | None:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return None
    return number if 0 < number < 100000 else None


def _date(value: Any) -> str | None:
    if not value:
        return None
    text = str(value)[:10]
    try:
        return datetime.strptime(text, "%Y-%m-%d").date().isoformat()
    except ValueError:
        return None


def _item_dict(row: tuple, lists: list[str]) -> dict:
    record = dict(zip(ITEM_COLUMNS, row))
    record["authors"] = json.loads(record["authors"] or "[]")
    record["tags"] = json.loads(record["tags"] or "[]")
    record["important"] = bool(record["important"])
    record["read_later"] = bool(record["read_later"])
    record["list_ids"] = lists
    return record


def _task_dict(row: tuple) -> dict:
    record = dict(zip(TASK_COLUMNS, row))
    record["done"] = bool(record["done"])
    return record
