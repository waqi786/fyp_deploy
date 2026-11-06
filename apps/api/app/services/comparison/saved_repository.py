"""Saved comparisons: a name, focus and column set per (owner, comparison).

The PDFs themselves stay in ``comparison_pdf_files``; this table only remembers what the owner called the comparison.
A comparison with stored PDFs but no saved row is still listed (named after its first PDF), so nothing is ever hidden.
Works on the same SQLite / Postgres database as ComparisonPdfRepository.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone

from app.services.comparison.uploads.repository import ComparisonPdfRepository

MAX_NAME = 160
MAX_FOCUS = 300
MAX_COLUMNS = 30


def _iso(value) -> str:
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value or "")


def _sqlite(connection) -> bool:
    return isinstance(connection, sqlite3.Connection)


class ComparisonSavedRepository:
    @staticmethod
    def _ensure_schema(connection) -> None:
        ComparisonPdfRepository._ensure_schema(connection)
        statement = """
            create table if not exists comparison_saved (
                owner_user_id text not null,
                comparison_id text not null,
                name text,
                focus text,
                columns_json text not null default '[]',
                updated_at text not null,
                primary key (owner_user_id, comparison_id)
            )
        """
        if _sqlite(connection):
            connection.execute(statement)
        else:
            with ComparisonPdfRepository._cursor(connection) as cursor:
                cursor.execute(statement)

    @staticmethod
    def _q(connection, sql: str) -> str:
        return sql if _sqlite(connection) else sql.replace("?", "%s")

    @classmethod
    def list(cls, *, owner_id: str) -> list[dict]:
        with ComparisonPdfRepository._connection() as connection:
            cls._ensure_schema(connection)
            with ComparisonPdfRepository._cursor(connection) as cursor:
                cursor.execute(cls._q(connection, """
                    select comparison_id, count(*), max(created_at), min(original_name)
                    from comparison_pdf_files where owner_user_id=? group by comparison_id
                """), (owner_id,))
                files = {str(row[0]): row for row in cursor.fetchall()}
                cursor.execute(cls._q(connection, "select comparison_id, name, focus, columns_json, updated_at from comparison_saved where owner_user_id=?"), (owner_id,))
                saved = {str(row[0]): row for row in cursor.fetchall()}
        items = []
        for comparison_id, row in files.items():
            meta = saved.get(comparison_id)
            fallback = str(row[3] or "").removesuffix(".pdf").removesuffix(".PDF") or None
            updated = max(_iso(row[2]), _iso(meta[4]) if meta else "")
            items.append({
                "comparison_id": comparison_id,
                "name": (meta[1] if meta and meta[1] else fallback),
                "focus": meta[2] if meta else None,
                "columns": json.loads(meta[3] or "[]") if meta else [],
                "file_count": int(row[1]),
                "updated_at": updated,
            })
        return sorted(items, key=lambda item: item["updated_at"], reverse=True)

    @classmethod
    def upsert(cls, *, owner_id: str, comparison_id: str, name: str | None, default_name: str | None, focus: str | None, columns: list[str] | None) -> dict:
        now = datetime.now(timezone.utc).isoformat()
        clean_name = (name or "").strip()[:MAX_NAME] or None
        clean_default = (default_name or "").strip()[:MAX_NAME] or None
        clean_focus = (focus or "").strip()[:MAX_FOCUS] or None
        clean_columns = [str(item).strip()[:120] for item in (columns or []) if str(item).strip()][:MAX_COLUMNS]
        with ComparisonPdfRepository._connection() as connection:
            cls._ensure_schema(connection)
            with ComparisonPdfRepository._cursor(connection) as cursor:
                cursor.execute(cls._q(connection, "select name, focus, columns_json from comparison_saved where owner_user_id=? and comparison_id=?"), (owner_id, comparison_id))
                current = cursor.fetchone()
                if current is None:
                    cursor.execute(cls._q(connection, """
                        insert into comparison_saved (owner_user_id, comparison_id, name, focus, columns_json, updated_at)
                        values (?, ?, ?, ?, ?, ?)
                    """), (owner_id, comparison_id, clean_name or clean_default, clean_focus, json.dumps(clean_columns, ensure_ascii=False), now))
                else:
                    cursor.execute(cls._q(connection, """
                        update comparison_saved set name=?, focus=?, columns_json=?, updated_at=? where owner_user_id=? and comparison_id=?
                    """), (
                        clean_name if name is not None else current[0],
                        clean_focus if focus is not None else current[1],
                        json.dumps(clean_columns, ensure_ascii=False) if columns is not None else current[2],
                        now, owner_id, comparison_id,
                    ))
                connection.commit()
        return next((item for item in cls.list(owner_id=owner_id) if item["comparison_id"] == comparison_id), {
            "comparison_id": comparison_id, "name": clean_name or clean_default, "focus": clean_focus, "columns": clean_columns, "file_count": 0, "updated_at": now,
        })

    @classmethod
    def has_files(cls, *, owner_id: str, comparison_id: str) -> bool:
        with ComparisonPdfRepository._connection() as connection:
            cls._ensure_schema(connection)
            with ComparisonPdfRepository._cursor(connection) as cursor:
                if _sqlite(connection):
                    cursor.execute("select 1 from comparison_pdf_files where owner_user_id=? and comparison_id=? limit 1", (owner_id, comparison_id))
                else:
                    cursor.execute("select 1 from comparison_pdf_files where owner_user_id=%s and comparison_id::text=%s limit 1", (owner_id, comparison_id))
                return cursor.fetchone() is not None

    @classmethod
    def delete(cls, *, owner_id: str, comparison_id: str) -> int:
        """Delete the comparison's stored PDFs and its saved name. Returns how many PDFs were removed."""
        with ComparisonPdfRepository._connection() as connection:
            cls._ensure_schema(connection)
            with ComparisonPdfRepository._cursor(connection) as cursor:
                if _sqlite(connection):
                    cursor.execute("delete from comparison_pdf_files where owner_user_id=? and comparison_id=?", (owner_id, comparison_id))
                else:
                    cursor.execute("delete from comparison_pdf_files where owner_user_id=%s and comparison_id::text=%s", (owner_id, comparison_id))
                removed = cursor.rowcount or 0
                cursor.execute(cls._q(connection, "delete from comparison_saved where owner_user_id=? and comparison_id=?"), (owner_id, comparison_id))
                connection.commit()
        return removed
