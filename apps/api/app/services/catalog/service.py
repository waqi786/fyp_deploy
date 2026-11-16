"""Read side of the research data pipeline (apps/pipeline): the deduplicated catalog, analytics and hybrid search.

CATALOG_DATABASE_URL  same value the pipeline writes to (default: storage/catalog.sqlite3 next to the API)
PIPELINE_OUTPUT_DIR   folder with analytics.json and index/ written by the pipeline (default: storage/pipeline)
CATALOG_ADMIN_USER_IDS  comma-separated accounts allowed to start pipeline runs in production

The search index is loaded once and reloaded automatically when the pipeline publishes a new one.
"""

from __future__ import annotations

import json
import logging
import os
import threading
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

API_ROOT = Path(__file__).resolve().parents[3]


def _db_url() -> str:
    return os.getenv("CATALOG_DATABASE_URL") or f"sqlite:///{API_ROOT / 'storage' / 'catalog.sqlite3'}"


def _output_dir() -> Path:
    return Path(os.getenv("PIPELINE_OUTPUT_DIR") or (API_ROOT / "storage" / "pipeline"))


class CatalogUnavailable(RuntimeError):
    pass


class CatalogService:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._index = None
        self._index_stamp: float | None = None
        self._papers: dict[str, dict[str, Any]] = {}
        self._running: dict[str, threading.Thread] = {}

    # ------------------------------------------------------------------ storage
    def db(self):  # noqa: ANN201
        try:
            from resora_pipeline.catalog_db import CatalogDB
        except ImportError as error:  # pragma: no cover - the API image installs apps/pipeline
            raise CatalogUnavailable("pipeline package not installed") from error
        return CatalogDB(_db_url())

    def _load_index(self):  # noqa: ANN202
        manifest = _output_dir() / "index" / "manifest.json"
        if not manifest.exists():
            return None
        stamp = manifest.stat().st_mtime
        with self._lock:
            if self._index is not None and self._index_stamp == stamp:
                return self._index
            from resora_pipeline.index import HybridIndex

            papers = {paper["paper_id"]: paper for paper in self.db().papers()}
            self._index = HybridIndex.load(manifest.parent, papers)
            self._papers = papers
            self._index_stamp = stamp
            return self._index

    # ------------------------------------------------------------------ reads
    def overview(self) -> dict[str, Any]:
        db = self.db()
        runs = db.runs(10)
        analytics = self.analytics()
        coverage = (analytics or {}).get("source_coverage") or {}
        last = next((run for run in runs if run["status"] == "succeeded"), None)
        etl = ((last or {}).get("stats") or {}).get("etl") or {}
        return {
            "papers": db.count(),
            "raw_records": etl.get("raw_records"),
            "duplicates_merged": coverage.get("duplicates_merged", etl.get("duplicates_merged")),
            "duplicate_rate": etl.get("duplicate_rate"),
            "papers_per_source": coverage.get("papers_per_source", {}),
            "unique_to_source": coverage.get("unique_to_source", {}),
            "papers_by_source_count": coverage.get("papers_by_source_count", {}),
            "last_run": last,
            "running": [run_id for run_id, thread in self._running.items() if thread.is_alive()],
            "index": json.loads((_output_dir() / "index" / "manifest.json").read_text()) if (_output_dir() / "index" / "manifest.json").exists() else None,
        }

    def analytics(self) -> dict[str, Any] | None:
        path = _output_dir() / "analytics.json"
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None

    def runs(self, limit: int = 20) -> list[dict[str, Any]]:
        return self.db().runs(limit)

    def paper(self, paper_id: str) -> dict[str, Any] | None:
        self._load_index()
        if paper_id in self._papers:
            return self._papers[paper_id]
        return next((paper for paper in self.db().papers() if paper["paper_id"] == paper_id), None)

    def search(self, query: str, *, limit: int = 20, year_from: int | None = None, year_to: int | None = None, open_access: bool | None = None) -> dict[str, Any]:
        index = self._load_index()
        if index is None:
            return {"query": query, "results": [], "index_ready": False}
        hits = index.search(query, top_k=min(200, limit * 4))
        results = []
        for hit in hits:
            paper = self._papers.get(hit["paper_id"])
            if not paper:
                continue
            if year_from and (paper.get("year") or 0) < year_from:
                continue
            if year_to and (paper.get("year") or 9999) > year_to:
                continue
            if open_access is not None and bool(paper.get("is_open_access")) != open_access:
                continue
            results.append({**paper, "match": {"score": hit["score"], "matched": hit["matched"], "keyword_score": hit["keyword_score"], "semantic_score": hit["semantic_score"]}})
            if len(results) >= limit:
                break
        return {"query": query, "results": results, "index_ready": True}

    # ------------------------------------------------------------------ runs
    def start_run(self, *, queries: list[str], sources: list[str], max_records: int, engine: str) -> str:
        from resora_pipeline.config import PipelineConfig
        from resora_pipeline.orchestrator import Pipeline, new_run_id

        if any(thread.is_alive() for thread in self._running.values()):
            raise RuntimeError("busy")
        run_id = new_run_id()
        config = PipelineConfig(catalog_database_url=_db_url(), output_dir=_output_dir())

        def work() -> None:
            try:
                Pipeline(config).run(queries=queries, sources=sources, engine=engine, max_records=max_records, run_id=run_id)
            except Exception:  # noqa: BLE001 - recorded in catalog_runs by the pipeline
                logger.exception("catalog run %s failed", run_id)

        thread = threading.Thread(target=work, name=f"catalog-run-{run_id}", daemon=True)
        self._running[run_id] = thread
        thread.start()
        return run_id


_service: CatalogService | None = None


def get_catalog_service() -> CatalogService:
    global _service
    if _service is None:
        _service = CatalogService()
    return _service
