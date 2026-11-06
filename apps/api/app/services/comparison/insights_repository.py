"""Owner-scoped persistence and content-addressed caching for Compare Insights."""
from __future__ import annotations

import hashlib
import json
import sqlite3
from uuid import uuid4

from app.services.comparison.uploads.repository import ComparisonPdfRepository

INSIGHTS_VERSION = 3


class ComparisonInsightsRepository:
    @staticmethod
    def _cache_key(file_hashes: list[str], columns: list[str], focus: str) -> str:
        material = json.dumps({"hashes": sorted(file_hashes), "columns": sorted(columns), "focus": focus, "version": INSIGHTS_VERSION}, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(material.encode()).hexdigest()

    @classmethod
    def _ensure_schema(cls, connection) -> None:
        if isinstance(connection, sqlite3.Connection):
            connection.executescript("""
                create table if not exists insight_runs (
                    id text primary key, comparison_id text not null, owner_user_id text not null,
                    cache_key text not null, status text not null, version integer not null,
                    started_at text not null default current_timestamp, finished_at text,
                    credits integer not null default 0, unique(owner_user_id, comparison_id, cache_key)
                );
                create table if not exists insight_sections (
                    run_id text not null, section_key text not null, status text not null,
                    data_json text not null, error text, generated_at text not null default current_timestamp,
                    primary key(run_id, section_key)
                );
                create table if not exists insight_feedback (
                    id text primary key, run_id text not null, owner_user_id text not null,
                    section_key text not null, value text not null, note text,
                    created_at text not null default current_timestamp
                );
                create table if not exists consensus_questions (
                    id text primary key, comparison_id text not null, owner_user_id text not null,
                    question text not null, result_json text not null, created_at text not null default current_timestamp
                );
                create table if not exists claim_checks (
                    id text primary key, comparison_id text not null, owner_user_id text not null,
                    claim text not null, result_json text not null, created_at text not null default current_timestamp
                );
                create index if not exists insight_runs_owner_idx on insight_runs(owner_user_id, comparison_id, started_at);
                create index if not exists insight_feedback_run_idx on insight_feedback(owner_user_id, run_id, section_key);
            """)
            return
        cursor = connection.cursor()
        try:
            cursor.execute("""
                create table if not exists insight_runs (
                    id text primary key, comparison_id text not null, owner_user_id text not null,
                    cache_key char(64) not null, status text not null, version integer not null,
                    started_at timestamptz not null default now(), finished_at timestamptz,
                    credits integer not null default 0, unique(owner_user_id, comparison_id, cache_key)
                )
            """)
            cursor.execute("""
                create table if not exists insight_sections (
                    run_id text not null, section_key text not null, status text not null,
                    data_json text not null, error text, generated_at timestamptz not null default now(),
                    primary key(run_id, section_key)
                )
            """)
            cursor.execute("""create table if not exists insight_feedback (
                id text primary key, run_id text not null, owner_user_id text not null,
                section_key text not null, value text not null, note text,
                created_at timestamptz not null default now())""")
            cursor.execute("""create table if not exists consensus_questions (
                id text primary key, comparison_id text not null, owner_user_id text not null,
                question text not null, result_json text not null, created_at timestamptz not null default now())""")
            cursor.execute("""create table if not exists claim_checks (
                id text primary key, comparison_id text not null, owner_user_id text not null,
                claim text not null, result_json text not null, created_at timestamptz not null default now())""")
            cursor.execute("create index if not exists insight_runs_owner_idx on insight_runs(owner_user_id, comparison_id, started_at)")
            cursor.execute("create index if not exists insight_feedback_run_idx on insight_feedback(owner_user_id, run_id, section_key)")
        finally:
            cursor.close()

    @classmethod
    def save_run(cls, *, owner_id: str, comparison_id: str, file_hashes: list[str], columns: list[str], focus: str, profiles: list[dict], insights_model: dict | None = None) -> tuple[str, bool]:
        cache_key = cls._cache_key(file_hashes, columns, focus)
        run_id = str(uuid4())
        with ComparisonPdfRepository._connection() as connection:
            cls._ensure_schema(connection)
            cursor = connection.cursor()
            try:
                marker = "?" if isinstance(connection, sqlite3.Connection) else "%s"
                cursor.execute(f"select id from insight_runs where owner_user_id={marker} and comparison_id={marker} and cache_key={marker}", (owner_id, comparison_id, cache_key))
                existing = cursor.fetchone()
                if existing:
                    return str(existing[0]), True
                if isinstance(connection, sqlite3.Connection):
                    cursor.execute("insert into insight_runs (id,comparison_id,owner_user_id,cache_key,status,version,finished_at) values (?,?,?,?,?,?,current_timestamp)", (run_id, comparison_id, owner_id, cache_key, "completed", INSIGHTS_VERSION))
                    cursor.execute("insert into insight_sections (run_id,section_key,status,data_json) values (?,?,?,?)", (run_id, "paper_profiles", "completed", json.dumps(profiles, ensure_ascii=False)))
                    if insights_model is not None:
                        cursor.execute("insert into insight_sections (run_id,section_key,status,data_json) values (?,?,?,?)", (run_id, "insights_model", "completed", json.dumps(insights_model, ensure_ascii=False)))
                else:
                    cursor.execute("insert into insight_runs (id,comparison_id,owner_user_id,cache_key,status,version,finished_at) values (%s,%s,%s,%s,%s,%s,now())", (run_id, comparison_id, owner_id, cache_key, "completed", INSIGHTS_VERSION))
                    cursor.execute("insert into insight_sections (run_id,section_key,status,data_json) values (%s,%s,%s,%s)", (run_id, "paper_profiles", "completed", json.dumps(profiles, ensure_ascii=False)))
                    if insights_model is not None:
                        cursor.execute("insert into insight_sections (run_id,section_key,status,data_json) values (%s,%s,%s,%s)", (run_id, "insights_model", "completed", json.dumps(insights_model, ensure_ascii=False)))
                connection.commit()
                return run_id, False
            finally:
                cursor.close()

    @classmethod
    def load_cached_analysis(cls, *, owner_id: str, comparison_id: str, file_hashes: list[str], columns: list[str], focus: str) -> tuple[str, list[dict], dict | None] | None:
        cache_key = cls._cache_key(file_hashes, columns, focus)
        with ComparisonPdfRepository._connection() as connection:
            cls._ensure_schema(connection)
            cursor = connection.cursor()
            try:
                marker = "?" if isinstance(connection, sqlite3.Connection) else "%s"
                cursor.execute(f"select r.id,s.section_key,s.data_json from insight_runs r join insight_sections s on s.run_id=r.id where r.owner_user_id={marker} and r.comparison_id={marker} and r.cache_key={marker} and r.status='completed' and s.section_key in ('paper_profiles','insights_model') and s.status='completed'", (owner_id, comparison_id, cache_key))
                records = cursor.fetchall()
                if not records:
                    return None
                sections = {str(record[1]): json.loads(record[2]) for record in records}
                if "paper_profiles" not in sections:
                    return None
                return str(records[0][0]), sections["paper_profiles"], sections.get("insights_model")
            finally:
                cursor.close()

    @classmethod
    def load_cached_profiles(cls, *, owner_id: str, comparison_id: str, file_hashes: list[str], columns: list[str], focus: str) -> tuple[str, list[dict]] | None:
        """Compatibility wrapper for existing callers that only need profiles."""
        cached = cls.load_cached_analysis(owner_id=owner_id, comparison_id=comparison_id, file_hashes=file_hashes, columns=columns, focus=focus)
        return (cached[0], cached[1]) if cached else None

    @classmethod
    def save_feedback(cls, *, owner_id: str, run_id: str, section_key: str, value: str, note: str | None = None) -> None:
        with ComparisonPdfRepository._connection() as connection:
            cls._ensure_schema(connection)
            cursor = connection.cursor()
            try:
                marker = "?" if isinstance(connection, sqlite3.Connection) else "%s"
                cursor.execute(f"select 1 from insight_runs where id={marker} and owner_user_id={marker}", (run_id, owner_id))
                if not cursor.fetchone():
                    raise PermissionError("Insights run not found.")
                values = (str(uuid4()), run_id, owner_id, section_key[:80], value, (note or "")[:1000] or None)
                if isinstance(connection, sqlite3.Connection):
                    cursor.execute("insert into insight_feedback (id,run_id,owner_user_id,section_key,value,note) values (?,?,?,?,?,?)", values)
                else:
                    cursor.execute("insert into insight_feedback (id,run_id,owner_user_id,section_key,value,note) values (%s,%s,%s,%s,%s,%s)", values)
                connection.commit()
            finally:
                cursor.close()

    @classmethod
    def save_interaction(cls, *, kind: str, owner_id: str, comparison_id: str, prompt: str, result: dict) -> str:
        if kind not in {"consensus_questions", "claim_checks"}:
            raise ValueError("Unsupported insight interaction.")
        record_id = str(uuid4())
        with ComparisonPdfRepository._connection() as connection:
            cls._ensure_schema(connection)
            cursor = connection.cursor()
            try:
                if isinstance(connection, sqlite3.Connection):
                    cursor.execute(f"insert into {kind} (id,comparison_id,owner_user_id,{ 'question' if kind == 'consensus_questions' else 'claim' },result_json) values (?,?,?,?,?)", (record_id, comparison_id, owner_id, prompt[:2000], json.dumps(result, ensure_ascii=False)))
                else:
                    cursor.execute(f"insert into {kind} (id,comparison_id,owner_user_id,{ 'question' if kind == 'consensus_questions' else 'claim' },result_json) values (%s,%s,%s,%s,%s)", (record_id, comparison_id, owner_id, prompt[:2000], json.dumps(result, ensure_ascii=False)))
                connection.commit()
                return record_id
            finally:
                cursor.close()
