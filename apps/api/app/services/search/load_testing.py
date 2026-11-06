"""Synthetic load-test helpers for the federated search service."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from statistics import mean
from time import perf_counter

from app.services.search.service import FederatedSearchService


@dataclass(slots=True)
class SearchLoadTestReport:
    concurrent_users: int
    requests_completed: int
    average_latency_ms: float
    max_latency_ms: float


class SearchLoadTester:
    """Runs a synthetic concurrent workload against the search service."""

    def __init__(self, service: FederatedSearchService) -> None:
        self.service = service

    async def run(
        self,
        *,
        concurrent_users: int,
        query: str,
        sources: list[str],
        limit: int = 10,
    ) -> SearchLoadTestReport:
        latencies: list[float] = []

        async def execute_once(index: int) -> None:
            started = perf_counter()
            await self.service.search(
                query,
                limit,
                sources,
                page=1,
                language="en",
                min_citations=0,
                open_access_only=False,
                study_type=None,
                quartile=None,
                sample_size_min=None,
            )
            latencies.append((perf_counter() - started) * 1000)

        await asyncio.gather(*(execute_once(index) for index in range(concurrent_users)))
        return SearchLoadTestReport(
            concurrent_users=concurrent_users,
            requests_completed=len(latencies),
            average_latency_ms=round(mean(latencies), 2) if latencies else 0.0,
            max_latency_ms=round(max(latencies), 2) if latencies else 0.0,
        )
