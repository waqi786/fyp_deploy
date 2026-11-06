"""Write tab persistence: documents (reviews and drafts) with version history, and screening projects with records.
Owner-scoped like the Library; tables are created on first use on the same database (SQLite or Postgres)."""

from __future__ import annotations

import json
from contextlib import contextmanager
from typing import Any
from uuid import uuid4

from app.core.config import settings
from app.services.library.store import (
    LibraryNotFound,
    LibraryStore,
    _Session,
    now,
    paper_key,
)

_SCHEMA = [
    """create table if not exists write_documents (
        id text primary key, owner_id text not null, kind text not null, title text not null, style text not null,
        language text not null default 'en', citation_style text not null default 'apa', project_id text,
        sources text not null default '[]', content text not null default '{}', created_at text not null, updated_at text not null
    )""",
    "create index if not exists write_documents_owner_idx on write_documents(owner_id, updated_at)",
    """create table if not exists write_versions (
        id text primary key, document_id text not null, owner_id text not null, label text not null, content text not null, created_at text not null
    )""",
    """create table if not exists write_screenings (
        id text primary key, owner_id text not null, name text not null, project_id text, criteria text not null default '',
        created_at text not null, updated_at text not null
    )""",
    """create table if not exists write_screening_records (
        id text primary key, screening_id text not null, owner_id text not null, record_key text not null, title text not null,
        authors text not null default '[]', year integer, venue text, doi text, abstract text, duplicate_of text,
        ta_decision text, ta_reason text, ft_decision text, ft_reason text, note text, library_item_id text,
        created_at text not null, updated_at text not null
    )""",
    "create index if not exists write_records_screening_idx on write_screening_records(screening_id)",
]
_READY: set[str] = set()
DOC_COLUMNS = ("id", "kind", "title", "style", "language", "citation_style", "project_id", "sources", "content", "created_at", "updated_at")
RECORD_COLUMNS = ("id", "record_key", "title", "authors", "year", "venue", "doi", "abstract", "duplicate_of", "ta_decision", "ta_reason", "ft_decision", "ft_reason", "note", "library_item_id", "created_at", "updated_at")
DECISIONS = ("include", "exclude", "maybe")
MAX_VERSIONS = 50


def _doc(row) -> dict[str, Any]:
    record = dict(zip(DOC_COLUMNS, row))
    record["sources"] = json.loads(record["sources"] or "[]")
    record["content"] = json.loads(record["content"] or "{}")
    return record


def _record(row) -> dict[str, Any]:
    record = dict(zip(RECORD_COLUMNS, row))
    record["authors"] = json.loads(record["authors"] or "[]")
    return record


class WriteStore:
    @contextmanager
    def _db(self):
        connection = LibraryStore._connect()
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

    # ------------------------------------------------------------------ documents

    def list_documents(self, owner: str) -> list[dict[str, Any]]:
        with self._db() as db:
            rows = db.all(f"select {', '.join(DOC_COLUMNS)} from write_documents where owner_id=? order by updated_at desc", (owner,))
        docs = [_doc(row) for row in rows]
        for doc in docs:
            sections = doc["content"].get("sections", [])
            doc["summary"] = {"sections": len(sections), "words": sum(len(str(section.get("text", "")).split()) for section in sections), "sources": len([s for s in doc["sources"] if s])}
            doc.pop("content")
        return docs

    def create_document(self, owner: str, data: dict[str, Any]) -> dict[str, Any]:
        doc_id = str(uuid4())
        stamp = now()
        with self._db() as db:
            db.run(
                "insert into write_documents (id, owner_id, kind, title, style, language, citation_style, project_id, sources, content, created_at, updated_at) values (?,?,?,?,?,?,?,?,?,?,?,?)",
                (doc_id, owner, data["kind"], data["title"][:300], data["style"], data.get("language") or "en", data.get("citation_style") or "apa", data.get("project_id"),
                 json.dumps(data.get("sources") or [], ensure_ascii=False), json.dumps(data.get("content") or {"sections": []}, ensure_ascii=False), stamp, stamp),
            )
        return self.get_document(owner, doc_id)

    def get_document(self, owner: str, doc_id: str) -> dict[str, Any]:
        with self._db() as db:
            row = db.one(f"select {', '.join(DOC_COLUMNS)} from write_documents where id=? and owner_id=?", (doc_id, owner))
        if not row:
            raise LibraryNotFound(doc_id)
        return _doc(row)

    def update_document(self, owner: str, doc_id: str, changes: dict[str, Any]) -> dict[str, Any]:
        current = self.get_document(owner, doc_id)
        merged = {**current, **{key: value for key, value in changes.items() if value is not None}}
        with self._db() as db:
            db.run(
                "update write_documents set title=?, style=?, language=?, citation_style=?, sources=?, content=?, updated_at=? where id=? and owner_id=?",
                (str(merged["title"])[:300], merged["style"], merged["language"], merged["citation_style"], json.dumps(merged["sources"], ensure_ascii=False),
                 json.dumps(merged["content"], ensure_ascii=False), now(), doc_id, owner),
            )
        return self.get_document(owner, doc_id)

    def delete_document(self, owner: str, doc_id: str) -> None:
        self.get_document(owner, doc_id)
        with self._db() as db:
            db.run("delete from write_versions where document_id=? and owner_id=?", (doc_id, owner))
            db.run("delete from write_documents where id=? and owner_id=?", (doc_id, owner))

    def save_version(self, owner: str, doc_id: str, label: str) -> dict[str, Any]:
        doc = self.get_document(owner, doc_id)
        version_id = str(uuid4())
        with self._db() as db:
            db.run("insert into write_versions (id, document_id, owner_id, label, content, created_at) values (?,?,?,?,?,?)",
                   (version_id, doc_id, owner, label[:120], json.dumps({"title": doc["title"], "content": doc["content"], "sources": doc["sources"]}, ensure_ascii=False), now()))
            extra = db.all("select id from write_versions where document_id=? and owner_id=? order by created_at desc", (doc_id, owner))[MAX_VERSIONS:]
            for (old_id,) in extra:
                db.run("delete from write_versions where id=?", (old_id,))
        return {"id": version_id, "label": label[:120]}

    def list_versions(self, owner: str, doc_id: str) -> list[dict[str, Any]]:
        self.get_document(owner, doc_id)
        with self._db() as db:
            rows = db.all("select id, label, content, created_at from write_versions where document_id=? and owner_id=? order by created_at desc", (doc_id, owner))
        result = []
        for version_id, label, content, created in rows:
            data = json.loads(content)
            words = sum(len(str(section.get("text", "")).split()) for section in data.get("content", {}).get("sections", []))
            result.append({"id": version_id, "label": label, "created_at": created, "words": words})
        return result

    def restore_version(self, owner: str, doc_id: str, version_id: str) -> dict[str, Any]:
        self.get_document(owner, doc_id)
        with self._db() as db:
            row = db.one("select content from write_versions where id=? and document_id=? and owner_id=?", (version_id, doc_id, owner))
        if not row:
            raise LibraryNotFound(version_id)
        data = json.loads(row[0])
        self.save_version(owner, doc_id, "Before restore")
        return self.update_document(owner, doc_id, {"title": data["title"], "content": data["content"], "sources": data["sources"]})

    # ------------------------------------------------------------------ screening

    def list_screenings(self, owner: str) -> list[dict[str, Any]]:
        with self._db() as db:
            rows = db.all("select id, name, project_id, criteria, created_at, updated_at from write_screenings where owner_id=? order by updated_at desc", (owner,))
            result = []
            for row in rows:
                record = dict(zip(("id", "name", "project_id", "criteria", "created_at", "updated_at"), row))
                records = db.all(f"select {', '.join(RECORD_COLUMNS)} from write_screening_records where screening_id=? and owner_id=?", (record["id"], owner))
                record["prisma"] = prisma([_record(item) for item in records])
                result.append(record)
        return result

    def create_screening(self, owner: str, name: str, project_id: str | None, criteria: str) -> dict[str, Any]:
        screening_id = str(uuid4())
        stamp = now()
        with self._db() as db:
            db.run("insert into write_screenings (id, owner_id, name, project_id, criteria, created_at, updated_at) values (?,?,?,?,?,?,?)",
                   (screening_id, owner, name[:200], project_id, criteria[:4000], stamp, stamp))
        return self.get_screening(owner, screening_id)

    def get_screening(self, owner: str, screening_id: str) -> dict[str, Any]:
        with self._db() as db:
            row = db.one("select id, name, project_id, criteria, created_at, updated_at from write_screenings where id=? and owner_id=?", (screening_id, owner))
            if not row:
                raise LibraryNotFound(screening_id)
            records = [_record(item) for item in db.all(f"select {', '.join(RECORD_COLUMNS)} from write_screening_records where screening_id=? and owner_id=? order by created_at, title", (screening_id, owner))]
        record = dict(zip(("id", "name", "project_id", "criteria", "created_at", "updated_at"), row))
        record["records"] = records
        record["prisma"] = prisma(records)
        return record

    def update_screening(self, owner: str, screening_id: str, name: str | None, criteria: str | None) -> dict[str, Any]:
        current = self.get_screening(owner, screening_id)
        with self._db() as db:
            db.run("update write_screenings set name=?, criteria=?, updated_at=? where id=? and owner_id=?",
                   ((name or current["name"])[:200], (criteria if criteria is not None else current["criteria"])[:4000], now(), screening_id, owner))
        return self.get_screening(owner, screening_id)

    def delete_screening(self, owner: str, screening_id: str) -> None:
        self.get_screening(owner, screening_id)
        with self._db() as db:
            db.run("delete from write_screening_records where screening_id=? and owner_id=?", (screening_id, owner))
            db.run("delete from write_screenings where id=? and owner_id=?", (screening_id, owner))

    def add_records(self, owner: str, screening_id: str, papers: list[dict[str, Any]]) -> dict[str, int]:
        """Every record is kept (PRISMA counts duplicates); repeats of an earlier record are marked duplicate_of."""
        self.get_screening(owner, screening_id)
        stamp = now()
        added = duplicates = 0
        with self._db() as db:
            existing = {key: record_id for record_id, key in db.all("select id, record_key from write_screening_records where screening_id=? and owner_id=? and duplicate_of is null", (screening_id, owner))}
            for paper in papers:
                title = str(paper.get("title") or "").strip()
                if not title:
                    continue
                key = paper_key(doi=paper.get("doi"), arxiv_id=paper.get("arxiv_id"), title=title, year=paper.get("year") if isinstance(paper.get("year"), int) else None)
                record_id = str(uuid4())
                duplicate_of = existing.get(key)
                db.run(
                    "insert into write_screening_records (id, screening_id, owner_id, record_key, title, authors, year, venue, doi, abstract, duplicate_of, library_item_id, created_at, updated_at) values (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (record_id, screening_id, owner, key, title[:600], json.dumps([str(name) for name in paper.get("authors") or []][:50], ensure_ascii=False),
                     paper.get("year") if isinstance(paper.get("year"), int) else None, paper.get("venue"), paper.get("doi"), (paper.get("abstract") or "")[:8000] or None,
                     duplicate_of, paper.get("library_item_id"), stamp, stamp),
                )
                if duplicate_of:
                    duplicates += 1
                else:
                    existing[key] = record_id
                    added += 1
            db.run("update write_screenings set updated_at=? where id=?", (stamp, screening_id))
        return {"added": added, "duplicates": duplicates}

    def decide(self, owner: str, screening_id: str, record_id: str, changes: dict[str, Any]) -> dict[str, Any]:
        screening = self.get_screening(owner, screening_id)
        record = next((item for item in screening["records"] if item["id"] == record_id), None)
        if not record:
            raise LibraryNotFound(record_id)
        merged = {**record, **{key: value for key, value in changes.items() if key in RECORD_COLUMNS}}
        if merged.get("ta_decision") != "include":
            merged["ft_decision"], merged["ft_reason"] = None, None
        with self._db() as db:
            db.run("update write_screening_records set ta_decision=?, ta_reason=?, ft_decision=?, ft_reason=?, note=?, updated_at=? where id=? and owner_id=?",
                   (merged.get("ta_decision"), (merged.get("ta_reason") or None), merged.get("ft_decision"), (merged.get("ft_reason") or None), (merged.get("note") or None), now(), record_id, owner))
            db.run("update write_screenings set updated_at=? where id=?", (now(), screening_id))
        return next(item for item in self.get_screening(owner, screening_id)["records"] if item["id"] == record_id)


def prisma(records: list[dict[str, Any]]) -> dict[str, Any]:
    unique = [record for record in records if not record.get("duplicate_of")]
    ta_excluded = [record for record in unique if record.get("ta_decision") == "exclude"]
    ta_included = [record for record in unique if record.get("ta_decision") == "include"]
    ft_excluded = [record for record in ta_included if record.get("ft_decision") == "exclude"]
    reasons: dict[str, int] = {}
    for record in ft_excluded:
        reason = (record.get("ft_reason") or "").strip() or "—"
        reasons[reason] = reasons.get(reason, 0) + 1
    return {
        "identified": len(records),
        "duplicates": len(records) - len(unique),
        "screened": len(unique),
        "screen_excluded": len(ta_excluded),
        "screen_pending": sum(1 for record in unique if record.get("ta_decision") in (None, "maybe")),
        "full_text_assessed": len(ta_included),
        "full_text_excluded": len(ft_excluded),
        "full_text_pending": sum(1 for record in ta_included if record.get("ft_decision") in (None, "maybe")),
        "full_text_reasons": [{"reason": reason, "count": count} for reason, count in sorted(reasons.items(), key=lambda pair: -pair[1])],
        "included": sum(1 for record in ta_included if record.get("ft_decision") == "include"),
    }
