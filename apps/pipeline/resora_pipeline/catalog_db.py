"""Load step of the ETL: write curated papers, run history and analytics into the catalog database.

SQLite by default (zero setup), PostgreSQL in production (`CATALOG_DATABASE_URL=postgresql://…`). The API reads these
tables (apps/api/app/services/catalog) — the schema below is the contract between the two.
Upserts are idempotent: re-running a pipeline over the same raw data produces the same rows.
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterable
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

SCHEMA = [
    """CREATE TABLE IF NOT EXISTS catalog_papers (
        paper_id TEXT PRIMARY KEY, doi TEXT, arxiv_id TEXT, title TEXT NOT NULL, abstract TEXT, year INTEGER,
        publication_date TEXT, venue TEXT, type TEXT, authors_json TEXT NOT NULL, topics_json TEXT NOT NULL,
        citation_count INTEGER NOT NULL DEFAULT 0, reference_count INTEGER NOT NULL DEFAULT 0,
        is_open_access INTEGER NOT NULL DEFAULT 0, oa_url TEXT, pdf_url TEXT, language TEXT,
        sources_json TEXT NOT NULL, source_records_json TEXT NOT NULL, duplicate_count INTEGER NOT NULL DEFAULT 0,
        first_run_id TEXT, last_run_id TEXT, updated_at TEXT NOT NULL)""",
    "CREATE INDEX IF NOT EXISTS ix_catalog_papers_doi ON catalog_papers (doi)",
    "CREATE INDEX IF NOT EXISTS ix_catalog_papers_year ON catalog_papers (year)",
    """CREATE TABLE IF NOT EXISTS catalog_runs (
        run_id TEXT PRIMARY KEY, engine TEXT NOT NULL, status TEXT NOT NULL, started_at TEXT NOT NULL,
        finished_at TEXT, params_json TEXT NOT NULL, stats_json TEXT NOT NULL, error TEXT)""",
    """CREATE TABLE IF NOT EXISTS catalog_analytics (
        run_id TEXT NOT NULL, kind TEXT NOT NULL, payload_json TEXT NOT NULL, created_at TEXT NOT NULL,
        PRIMARY KEY (run_id, kind))""",
]

PAPER_COLUMNS = (
    "paper_id", "doi", "arxiv_id", "title", "abstract", "year", "publication_date", "venue", "type", "authors_json", "topics_json",
    "citation_count", "reference_count", "is_open_access", "oa_url", "pdf_url", "language", "sources_json", "source_records_json",
    "duplicate_count", "first_run_id", "last_run_id", "updated_at",
)


def _now() -> str:
    return datetime.now(UTC).isoformat()


class CatalogDB:
    def __init__(self, url: str) -> None:
        self.url = url
        self.postgres = url.startswith(("postgresql://", "postgres://"))
        if not self.postgres:
            path = url.removeprefix("sqlite:///")
            Path(path).parent.mkdir(parents=True, exist_ok=True)
            self.path = path
        with self.connect() as connection:
            for statement in SCHEMA:
                connection.execute(statement)

    @contextmanager
    def connect(self):
        if self.postgres:  # pragma: no cover - exercised in docker-compose
            import psycopg

            with psycopg.connect(self.url) as connection:
                yield _PgAdapter(connection)
            return
        connection = sqlite3.connect(self.path, timeout=30)
        connection.row_factory = sqlite3.Row
        try:
            connection.execute("PRAGMA journal_mode=WAL")
            yield connection
            connection.commit()
        finally:
            connection.close()

    # ----------------------------------------------------------------- papers
    def upsert_papers(self, papers: Iterable[dict[str, Any]], *, run_id: str) -> int:
        now = _now()
        rows = []
        for paper in papers:
            rows.append((
                paper["paper_id"], paper.get("doi"), paper.get("arxiv_id"), paper.get("title") or "", paper.get("abstract") or "", paper.get("year"),
                paper.get("publication_date"), paper.get("venue"), paper.get("type"), json.dumps(paper.get("authors") or [], ensure_ascii=False),
                json.dumps(paper.get("topics") or [], ensure_ascii=False), int(paper.get("citation_count") or 0), int(paper.get("reference_count") or 0),
                1 if paper.get("is_open_access") else 0, paper.get("oa_url"), paper.get("pdf_url"), paper.get("language"),
                json.dumps(paper.get("sources") or []), json.dumps(paper.get("source_records") or []), int(paper.get("duplicate_count") or 0),
                run_id, run_id, now,
            ))
        if not rows:
            return 0
        placeholders = ",".join("?" for _ in PAPER_COLUMNS)
        updates = ",".join(f"{column}=excluded.{column}" for column in PAPER_COLUMNS if column not in ("paper_id", "first_run_id"))
        sql = f"INSERT INTO catalog_papers ({','.join(PAPER_COLUMNS)}) VALUES ({placeholders}) ON CONFLICT(paper_id) DO UPDATE SET {updates}"
        with self.connect() as connection:
            connection.executemany(sql, rows)
        return len(rows)

    def papers(self, limit: int | None = None) -> list[dict[str, Any]]:
        sql = "SELECT * FROM catalog_papers ORDER BY paper_id" + (f" LIMIT {int(limit)}" if limit else "")
        with self.connect() as connection:
            return [decode_paper(dict(row)) for row in connection.execute(sql).fetchall()]

    def count(self) -> int:
        with self.connect() as connection:
            return int(connection.execute("SELECT COUNT(*) FROM catalog_papers").fetchone()[0])

    # ----------------------------------------------------------------- runs + analytics
    def start_run(self, run_id: str, engine: str, params: dict[str, Any]) -> None:
        with self.connect() as connection:
            connection.execute(
                "INSERT INTO catalog_runs (run_id, engine, status, started_at, params_json, stats_json) VALUES (?,?,?,?,?,?) "
                "ON CONFLICT(run_id) DO UPDATE SET status=excluded.status, started_at=excluded.started_at",
                (run_id, engine, "running", _now(), json.dumps(params), "{}"),
            )

    def finish_run(self, run_id: str, *, status: str, stats: dict[str, Any], error: str | None = None) -> None:
        with self.connect() as connection:
            connection.execute("UPDATE catalog_runs SET status=?, finished_at=?, stats_json=?, error=? WHERE run_id=?", (status, _now(), json.dumps(stats), error, run_id))

    def runs(self, limit: int = 20) -> list[dict[str, Any]]:
        with self.connect() as connection:
            rows = connection.execute("SELECT * FROM catalog_runs ORDER BY started_at DESC LIMIT ?", (limit,)).fetchall()
        return [{**dict(row), "params": json.loads(row["params_json"]), "stats": json.loads(row["stats_json"])} for row in rows]

    def save_analytics(self, run_id: str, analytics: dict[str, Any]) -> None:
        now = _now()
        with self.connect() as connection:
            connection.executemany(
                "INSERT INTO catalog_analytics (run_id, kind, payload_json, created_at) VALUES (?,?,?,?) "
                "ON CONFLICT(run_id, kind) DO UPDATE SET payload_json=excluded.payload_json, created_at=excluded.created_at",
                [(run_id, kind, json.dumps(payload, ensure_ascii=False), now) for kind, payload in analytics.items()],
            )


def decode_paper(row: dict[str, Any]) -> dict[str, Any]:
    paper = dict(row)
    for column, key in (("authors_json", "authors"), ("topics_json", "topics"), ("sources_json", "sources"), ("source_records_json", "source_records")):
        paper[key] = json.loads(paper.pop(column) or "[]")
    paper["is_open_access"] = bool(paper.get("is_open_access"))
    return paper


class _PgAdapter:  # pragma: no cover - thin shim so the same SQL runs on PostgreSQL
    def __init__(self, connection: Any) -> None:
        self.connection = connection

    def execute(self, sql: str, params: tuple = ()):  # noqa: ANN201
        cursor = self.connection.cursor()
        cursor.execute(sql.replace("?", "%s"), params)
        return _PgCursor(cursor)

    def executemany(self, sql: str, rows: list[tuple]) -> None:
        with self.connection.cursor() as cursor:
            cursor.executemany(sql.replace("?", "%s"), rows)


class _PgCursor:  # pragma: no cover
    def __init__(self, cursor: Any) -> None:
        self.cursor = cursor

    def fetchone(self):  # noqa: ANN201
        return self.cursor.fetchone()

    def fetchall(self):  # noqa: ANN201
        names = [column.name for column in self.cursor.description or []]
        return [_Row(dict(zip(names, row))) for row in self.cursor.fetchall()]


class _Row(dict):  # pragma: no cover
    def __getitem__(self, key):  # noqa: ANN001, ANN204
        if isinstance(key, int):
            return list(self.values())[key]
        return super().__getitem__(key)
