"""End-to-end pipeline: collect → raw lake → ETL (normalize + deduplicate) → catalog DB → analytics → search index.

Two engines run the same stages:
  * engine="local": pure Python, for development, tests and datasets up to ~100k records.
  * engine="spark": PySpark jobs (spark/etl_job.py, spark/analytics_job.py) for large datasets / clusters.

Stages are chained through the event bus, so in production a Kafka consumer (or the Airflow DAG) can run each
stage as a separate task. Every run is recorded in catalog_runs with its parameters and statistics.
"""

from __future__ import annotations

import logging
import time
import uuid
from collections.abc import Iterable
from datetime import UTC, datetime
from typing import Any

from resora_pipeline import analytics as A
from resora_pipeline.catalog_db import CatalogDB
from resora_pipeline.collectors.sources import COLLECTORS
from resora_pipeline.config import PipelineConfig
from resora_pipeline.dedup import deduplicate
from resora_pipeline.events import EventBus, make_bus
from resora_pipeline.index import Embedder, HybridIndex
from resora_pipeline.lake import DataLake, open_storage
from resora_pipeline.normalize import normalize_envelope

logger = logging.getLogger(__name__)


def new_run_id() -> str:
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:6]


class Pipeline:
    def __init__(self, config: PipelineConfig | None = None, *, lake: DataLake | None = None, bus: EventBus | None = None, db: CatalogDB | None = None) -> None:
        self.config = config or PipelineConfig()
        self.lake = lake or DataLake(open_storage(self.config.lake_uri, endpoint_url=self.config.s3_endpoint_url, access_key=self.config.s3_access_key, secret_key=self.config.s3_secret_key, region=self.config.s3_region))
        self.bus = bus or make_bus(self.config.kafka_bootstrap_servers, self.lake)
        self.db = db or CatalogDB(self.config.catalog_database_url)

    # ------------------------------------------------------------------ 1-2. ingestion
    def ingest(self, queries: Iterable[str], *, sources: Iterable[str], run_id: str, max_records: int = 200, since: str | None = None, clients: dict[str, Any] | None = None) -> dict[str, Any]:
        results = []
        for source in sources:
            collector_cls = COLLECTORS.get(source)
            if collector_cls is None:
                raise ValueError(f"unknown source {source}")
            collector = collector_cls(self.config, self.lake, client=(clients or {}).get(source))
            for query in queries:
                results.append(collector.collect(query, run_id=run_id, since=since, max_records=max_records).as_dict())
        summary = {"run_id": run_id, "collections": results, "records": sum(r["records"] for r in results)}
        self.bus.publish("raw.ingested", summary)
        return summary

    # ------------------------------------------------------------------ 3-5. ETL
    def etl_local(self, *, run_id: str, sources: Iterable[str] | None = None, only_run: bool = False) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        started = time.perf_counter()
        raw_count = dropped = 0
        normalized = []
        for envelope in self.lake.read_raw(sources=sources, run_id=run_id if only_run else None):
            raw_count += 1
            record = normalize_envelope(envelope)
            if record is None:
                dropped += 1
            else:
                normalized.append(record)
        papers, stats = deduplicate(normalized)
        written = self.db.upsert_papers(papers, run_id=run_id)
        self.lake.write_jsonl(f"curated/papers/run={run_id}/papers.jsonl.gz", papers)
        result = {"run_id": run_id, "raw_records": raw_count, "dropped_invalid": dropped, "normalized": len(normalized), **stats.as_dict(), "papers_written": written, "seconds": round(time.perf_counter() - started, 3)}
        self.bus.publish("etl.completed", result)
        return papers, result

    # ------------------------------------------------------------------ 6. analytics
    def analyze(self, papers: list[dict[str, Any]] | None = None, *, run_id: str) -> dict[str, Any]:
        papers = papers if papers is not None else self.db.papers()
        output = A.run_all(papers, current_year=datetime.now(UTC).year)
        self.db.save_analytics(run_id, output)
        self.lake.write_json(f"analytics/run={run_id}/analytics.json", output)
        self.config.output_dir.mkdir(parents=True, exist_ok=True)
        (self.config.output_dir / "analytics.json").write_text(__import__("json").dumps({"run_id": run_id, **output}, ensure_ascii=False, indent=2), encoding="utf-8")
        self.bus.publish("analytics.completed", {"run_id": run_id, "paper_count": output["paper_count"], "hot_topics": len(output["hot_topics"]), "gap_candidates": len(output["gap_candidates"])})
        return output

    # ------------------------------------------------------------------ 7. search index
    def build_index(self, papers: list[dict[str, Any]] | None = None, *, run_id: str) -> dict[str, Any]:
        papers = papers if papers is not None else self.db.papers()
        index = HybridIndex(papers, Embedder(self.config.embedder))
        manifest = index.save(self.config.output_dir / "index")
        manifest["run_id"] = run_id
        self.bus.publish("index.completed", manifest)
        return manifest

    # ------------------------------------------------------------------ full run
    def run(self, *, queries: list[str], sources: list[str], engine: str = "local", max_records: int = 200, since: str | None = None, skip_ingest: bool = False, clients: dict[str, Any] | None = None, run_id: str | None = None) -> dict[str, Any]:
        run_id = run_id or new_run_id()
        params = {"queries": queries, "sources": sources, "engine": engine, "max_records": max_records, "since": since, "skip_ingest": skip_ingest}
        self.db.start_run(run_id, engine, params)
        stats: dict[str, Any] = {}
        try:
            if not skip_ingest:
                stats["ingest"] = self.ingest(queries, sources=sources, run_id=run_id, max_records=max_records, since=since, clients=clients)
            if engine == "spark":
                from resora_pipeline.spark.etl_job import run_spark_etl

                stats["etl"] = run_spark_etl(self.config, self.lake, self.db, run_id=run_id)
                self.bus.publish("etl.completed", stats["etl"])
                papers = self.db.papers()
            else:
                papers, stats["etl"] = self.etl_local(run_id=run_id)
            analytics = self.analyze(papers, run_id=run_id)
            stats["analytics"] = {"paper_count": analytics["paper_count"], "hot_topics": len(analytics["hot_topics"]), "gap_candidates": len(analytics["gap_candidates"])}
            stats["index"] = self.build_index(papers, run_id=run_id)
            self.db.finish_run(run_id, status="succeeded", stats=stats)
        except Exception as error:
            logger.exception("pipeline run %s failed", run_id)
            self.db.finish_run(run_id, status="failed", stats=stats, error=f"{type(error).__name__}: {error}"[:500])
            raise
        return {"run_id": run_id, **stats}
