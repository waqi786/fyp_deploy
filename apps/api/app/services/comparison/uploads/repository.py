"""Private persistence for PDFs used by Compare.

PDF bytes and extraction text are stored in PostgreSQL so they survive API restarts.
Every read and delete is scoped to the authenticated owner.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
from contextlib import contextmanager
from uuid import uuid4

from app.core.config import settings


class ComparisonPdfRepository:
    @staticmethod
    def _paper_title(filename: str, extracted_text: str) -> str:
        pages = re.split(r"\[PDF page \d+\]", extracted_text, maxsplit=1)
        first_page = pages[1] if len(pages) > 1 else extracted_text[:5000]
        lines = [" ".join(line.split()) for line in first_page.splitlines() if line.strip()]
        ignored = re.compile(r"journal|conference|proceedings|issn|copyright|open access|license|licence|creative ?commons|cc by|review article|research article|preprint submitted|abstract|keywords?|\bvolume\b|\bvol\.?\b|\bissue\b|\bpages?\s+\d+|\b(?:january|february|march|april|may|june|july|august|september|october|november|december)\b", re.IGNORECASE)
        title_start = next((index for index, line in enumerate(lines) if len(line) >= 12 and not ignored.search(line) and not re.match(r"^(?:\d+\.?\s*)?(?:university|department|school|faculty|email|https?://)", line, re.IGNORECASE)), None)
        if title_start is None:
            return os.path.splitext(filename)[0]
        title_lines = []
        for line in lines[title_start:title_start + 4]:
            if ignored.search(line) or re.search(r"\b(?:university|department|faculty|school|@)\b", line, re.IGNORECASE):
                break
            if re.search(r"\b[A-Z][a-z]+\s+[A-Z][a-z]+\s*\d*,\s*[A-Z][a-z]+\s+[A-Z][a-z]+\s*\d*\b", line):
                break
            if len(line) < 5 or len(line) > 130:
                break
            title_lines.append(line)
            if line.endswith((".", "?")):
                break
        title = re.sub(r"\s+", " ", " ".join(title_lines)).strip(" .")
        if re.match(r"^(?:a full paper|synthetic research paper|test paper)\b", title, re.IGNORECASE):
            return os.path.splitext(filename)[0]
        return title[:220] if len(title) >= 12 else os.path.splitext(filename)[0]

    @staticmethod
    @contextmanager
    def _cursor(connection):
        cursor = connection.cursor()
        try:
            yield cursor
        finally:
            cursor.close()

    @classmethod
    @contextmanager
    def _connection(cls):
        connection = cls._connect()
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    @staticmethod
    def _connect():
        if settings.database_url.startswith("sqlite:///"):
            path = settings.database_url.removeprefix("sqlite:///")
            parent = os.path.dirname(path)
            if parent:
                os.makedirs(parent, exist_ok=True)
            connection = sqlite3.connect(path, timeout=10)
            connection.row_factory = None
            return connection
        import psycopg

        dsn = settings.database_url.replace("postgresql+psycopg://", "postgresql://", 1)
        return psycopg.connect(dsn, connect_timeout=5)

    @classmethod
    def _ensure_schema(cls, connection) -> None:
        if isinstance(connection, sqlite3.Connection):
            connection.executescript("""
                create table if not exists comparison_pdf_files (
                    id text primary key,
                    comparison_id text not null,
                    owner_user_id text not null,
                    original_name text not null,
                    sha256 text not null,
                    size_bytes integer not null,
                    page_count integer not null,
                    extracted_text text not null,
                    extraction_method text not null,
                    parsed_tables text not null default '[]',
                    pdf_bytes blob not null,
                    created_at text not null default current_timestamp,
                    unique (comparison_id, owner_user_id, sha256)
                );
                create index if not exists comparison_pdf_owner_idx on comparison_pdf_files(owner_user_id, comparison_id, created_at);
            """)
            connection.execute("alter table comparison_pdf_files add column parsed_tables text not null default '[]'") if "parsed_tables" not in {row[1] for row in connection.execute("pragma table_info(comparison_pdf_files)").fetchall()} else None
            return
        with cls._cursor(connection) as cursor:
            cursor.execute("""
                create table if not exists comparison_pdf_files (
                    id uuid primary key,
                    comparison_id uuid not null,
                    owner_user_id text not null,
                    original_name text not null,
                    sha256 char(64) not null,
                    size_bytes bigint not null,
                    page_count integer not null,
                    extracted_text text not null,
                    extraction_method text not null,
                    parsed_tables text not null default '[]',
                    pdf_bytes bytea not null,
                    created_at timestamptz not null default now(),
                    unique (comparison_id, owner_user_id, sha256)
                )
            """)
            cursor.execute("alter table comparison_pdf_files add column if not exists parsed_tables text not null default '[]'")
            cursor.execute("create index if not exists comparison_pdf_owner_idx on comparison_pdf_files(owner_user_id, comparison_id, created_at)")

    @classmethod
    def save(cls, *, owner_id: str, comparison_id: str, name: str, data: bytes, page_count: int, text: str, method: str, parsed_tables: list[dict] | None = None) -> dict:
        file_id = str(uuid4())
        digest = hashlib.sha256(data).hexdigest()
        with cls._connection() as connection:
            cls._ensure_schema(connection)
            with cls._cursor(connection) as cursor:
                statement = """
                    insert into comparison_pdf_files
                    (id, comparison_id, owner_user_id, original_name, sha256, size_bytes, page_count, extracted_text, extraction_method, parsed_tables, pdf_bytes)
                    values ({}, {}, {}, {}, {}, {}, {}, {}, {}, {}, {})
                    on conflict (comparison_id, owner_user_id, sha256) do update set original_name = excluded.original_name
                    returning id, original_name, sha256, size_bytes, page_count, extraction_method
                """
                if isinstance(connection, sqlite3.Connection):
                    statement = statement.format(*["?"] * 11)
                else:
                    statement = statement.format(*["%s"] * 11)
                cursor.execute(statement, (file_id, comparison_id, owner_id, name, digest, len(data), page_count, text, method, json.dumps(parsed_tables or [], ensure_ascii=False), data))
                row = cursor.fetchone()
                connection.commit()
        return {"id": str(row[0]), "name": row[1], "sha256": row[2].strip(), "size": row[3], "pages": row[4], "extraction_method": row[5]}

    @classmethod
    def list(cls, *, owner_id: str, comparison_id: str) -> list[dict]:
        with cls._connection() as connection:
            cls._ensure_schema(connection)
            with cls._cursor(connection) as cursor:
                if isinstance(connection, sqlite3.Connection):
                    cursor.execute("select id, original_name, sha256, size_bytes, page_count, extraction_method, created_at from comparison_pdf_files where owner_user_id=? and comparison_id=? order by created_at", (owner_id, comparison_id))
                else:
                    cursor.execute("select id, original_name, sha256, size_bytes, page_count, extraction_method, created_at from comparison_pdf_files where owner_user_id=%s and comparison_id=%s order by created_at", (owner_id, comparison_id))
                return [{"id": str(r[0]), "name": r[1], "sha256": r[2].strip(), "size": r[3], "pages": r[4], "extraction_method": r[5], "created_at": r[6].isoformat() if hasattr(r[6], "isoformat") else str(r[6])} for r in cursor.fetchall()]

    @classmethod
    def load_papers(cls, *, owner_id: str, comparison_id: str, file_ids: list[str]) -> list[dict]:
        with cls._connection() as connection:
            cls._ensure_schema(connection)
            with cls._cursor(connection) as cursor:
                if isinstance(connection, sqlite3.Connection):
                    markers = ",".join("?" for _ in file_ids)
                    cursor.execute(f"select id, original_name, page_count, extracted_text, parsed_tables from comparison_pdf_files where owner_user_id=? and comparison_id=? and id in ({markers})", [owner_id, comparison_id, *file_ids])
                else:
                    cursor.execute("select id, original_name, page_count, extracted_text, parsed_tables from comparison_pdf_files where owner_user_id=%s and comparison_id=%s and id = any(%s::uuid[])", (owner_id, comparison_id, file_ids))
                rows = cursor.fetchall()
        found = {str(row[0]): row for row in rows}
        if len(found) != len(set(file_ids)):
            raise PermissionError("One or more uploaded PDFs are unavailable to this account.")
        return [{"paper_id": f"pdf:{row[0]}", "title": cls._paper_title(row[1], row[3]), "abstract": None, "full_text": row[3], "parsed_tables": json.loads(row[4] or "[]"), "full_text_status": "provided", "full_text_source": "Uploaded PDF", "year": None, "venue": "Uploaded PDF", "url": None, "pdf_url": None, "pdf_urls": [], "citation_count": 0, "reference_count": 0, "is_open_access": False, "authors": [], "source": "uploaded_pdf", "all_sources": ["uploaded_pdf"], "external_ids": {}} for file_id in file_ids for row in [found[file_id]]]

    @classmethod
    def read_pdf(cls, *, owner_id: str, file_id: str) -> tuple[str, bytes] | None:
        with cls._connection() as connection:
            cls._ensure_schema(connection)
            with cls._cursor(connection) as cursor:
                if isinstance(connection, sqlite3.Connection):
                    cursor.execute("select original_name, pdf_bytes from comparison_pdf_files where owner_user_id=? and id=?", (owner_id, file_id))
                else:
                    cursor.execute("select original_name, pdf_bytes from comparison_pdf_files where owner_user_id=%s and id=%s", (owner_id, file_id))
                row = cursor.fetchone()
        return (row[0], bytes(row[1])) if row else None

    @classmethod
    def delete(cls, *, owner_id: str, file_id: str) -> bool:
        with cls._connection() as connection:
            cls._ensure_schema(connection)
            with cls._cursor(connection) as cursor:
                if isinstance(connection, sqlite3.Connection):
                    cursor.execute("delete from comparison_pdf_files where owner_user_id=? and id=?", (owner_id, file_id))
                else:
                    cursor.execute("delete from comparison_pdf_files where owner_user_id=%s and id=%s", (owner_id, file_id))
                removed = cursor.rowcount > 0
        return removed
