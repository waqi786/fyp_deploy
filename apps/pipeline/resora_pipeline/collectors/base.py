"""Shared collector machinery: polite rate limiting, retries with exponential backoff and jitter, Retry-After support,
incremental cursors and batched writes to the Data Lake.

Each concrete collector only implements `pages()` — a generator of raw records for one query — and is otherwise
identical, so adding a new source is a small, well-tested change.
"""

from __future__ import annotations

import logging
import random
import threading
import time
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import httpx

from resora_pipeline.config import PipelineConfig
from resora_pipeline.lake import DataLake

logger = logging.getLogger(__name__)


class RateLimiter:
    """Token bucket: at most `rate` requests per second with bursts up to `burst`."""

    def __init__(self, rate: float, burst: int = 1) -> None:
        self.rate = rate
        self.capacity = burst
        self.tokens = float(burst)
        self.updated = time.monotonic()
        self.lock = threading.Lock()

    def acquire(self) -> None:
        with self.lock:
            while True:
                now = time.monotonic()
                self.tokens = min(self.capacity, self.tokens + (now - self.updated) * self.rate)
                self.updated = now
                if self.tokens >= 1:
                    self.tokens -= 1
                    return
                time.sleep((1 - self.tokens) / self.rate)


@dataclass
class CollectResult:
    source: str
    run_id: str
    records: int
    files: list[str]
    pages: int
    errors: int
    cursor: dict[str, Any]

    def as_dict(self) -> dict[str, Any]:
        return {"source": self.source, "run_id": self.run_id, "records": self.records, "files": self.files, "pages": self.pages, "errors": self.errors}


class Collector:
    source = "base"
    rate_per_second = 1.0
    page_size = 100
    batch_size = 1000

    def __init__(self, config: PipelineConfig, lake: DataLake, *, client: httpx.Client | None = None, sleep: Any = time.sleep) -> None:
        self.config = config
        self.lake = lake
        self.client = client or httpx.Client(timeout=30, headers={"User-Agent": config.user_agent}, follow_redirects=True)
        self.limiter = RateLimiter(self.rate_per_second)
        self.sleep = sleep
        self.pages_fetched = 0
        self.errors = 0

    # ------------------------------------------------------------------ http
    def get(self, url: str, *, params: dict[str, Any] | None = None, headers: dict[str, str] | None = None, attempts: int = 5) -> httpx.Response:
        delay = 1.0
        for attempt in range(1, attempts + 1):
            self.limiter.acquire()
            try:
                response = self.client.get(url, params=params, headers=headers)
            except httpx.HTTPError as error:
                if attempt == attempts:
                    raise
                logger.info("%s: network error %s, retry %s", self.source, type(error).__name__, attempt)
            else:
                if response.status_code < 400:
                    self.pages_fetched += 1
                    return response
                if response.status_code not in (429, 500, 502, 503, 504) or attempt == attempts:
                    response.raise_for_status()
                retry_after = response.headers.get("Retry-After")
                if retry_after and retry_after.isdigit():
                    delay = max(delay, float(retry_after))
            self.sleep(delay + random.uniform(0, delay / 2))
            delay = min(delay * 2, 60)
        raise RuntimeError("unreachable")

    # ------------------------------------------------------------------ state
    def state_key(self) -> str:
        return f"state/{self.source}.json"

    def load_state(self) -> dict[str, Any]:
        return self.lake.read_json(self.state_key(), default={}) or {}

    def save_state(self, state: dict[str, Any]) -> None:
        self.lake.write_json(self.state_key(), state)

    # ------------------------------------------------------------------ collection
    def pages(self, query: str, *, since: str | None, max_records: int) -> Iterator[dict[str, Any]]:
        raise NotImplementedError

    def collect(self, query: str, *, run_id: str, since: str | None = None, max_records: int = 500, incremental: bool = True) -> CollectResult:
        """Fetch up to `max_records` raw records for `query` and write them to the raw zone in gzip JSONL batches."""
        state = self.load_state()
        query_state = state.get(query, {}) if incremental else {}
        since = since or query_state.get("last_success_date")
        started = datetime.now(UTC)
        ingest_date = started.date().isoformat()
        prefix = DataLake.raw_prefix(self.source, ingest_date, run_id)
        files: list[str] = []
        batch: list[dict[str, Any]] = []
        total = 0

        def flush() -> None:
            if batch:
                key = f"{prefix}/part-{len(files):05d}.jsonl.gz"
                self.lake.write_jsonl(key, batch)
                files.append(key)
                batch.clear()

        try:
            for raw in self.pages(query, since=since, max_records=max_records):
                batch.append({"source": self.source, "fetched_at": datetime.now(UTC).isoformat(), "query": query, "run_id": run_id, "raw": raw})
                total += 1
                if len(batch) >= self.batch_size:
                    flush()
                if total >= max_records:
                    break
        except httpx.HTTPError as error:
            self.errors += 1
            logger.warning("%s: collection stopped early (%s); keeping %s records", self.source, type(error).__name__, total)
        flush()
        if not self.errors:
            state[query] = {"last_success_date": ingest_date, "records": total, "run_id": run_id}
            self.save_state(state)
        return CollectResult(self.source, run_id, total, files, self.pages_fetched, self.errors, state.get(query, {}))
