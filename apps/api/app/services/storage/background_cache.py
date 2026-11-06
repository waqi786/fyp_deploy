import asyncio
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from app.schemas.paper import PaperRecord, SearchCacheStatus


def _chunked(items: list[PaperRecord], batch_size: int) -> Iterable[list[PaperRecord]]:
    for index in range(0, len(items), batch_size):
        yield items[index:index + batch_size]


@dataclass
class CacheStoreResult:
    inserted_batches: int
    total_items: int


@dataclass
class BackgroundPaperCache:
    freshness_window: timedelta = field(default_factory=lambda: timedelta(hours=72))
    storage: dict[str, tuple[PaperRecord, datetime]] = field(default_factory=dict)

    async def store_papers_background(self, papers: list[PaperRecord]) -> CacheStoreResult:
        inserted_batches = 0
        for batch in _chunked(papers, 50):
            await self._store_batch_with_backoff(batch)
            inserted_batches += 1
        return CacheStoreResult(inserted_batches=inserted_batches, total_items=len(papers))

    async def cache_search_results(self, papers: list[PaperRecord]) -> SearchCacheStatus:
        result = await self.store_papers_background(papers)
        return SearchCacheStatus(
            inserted_batches=result.inserted_batches,
            total_items=result.total_items,
            cached_at=datetime.now(UTC).isoformat(),
        )

    async def _store_batch_with_backoff(self, batch: list[PaperRecord]) -> None:
        delays = [1, 2, 4]
        for attempt, delay in enumerate(delays, start=1):
            try:
                now = datetime.now(UTC)
                for paper in batch:
                    self.storage[paper.paper_id] = (paper, now)
                return
            except Exception:  # noqa: BLE001
                if attempt == len(delays):
                    raise
                await asyncio.sleep(delay)

    def get_fresh(self, paper_id: str) -> PaperRecord | None:
        entry = self.storage.get(paper_id)
        if not entry:
            return None
        paper, inserted_at = entry
        if datetime.now(UTC) - inserted_at > self.freshness_window:
            return None
        return paper
