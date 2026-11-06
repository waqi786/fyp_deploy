"""Background worker process for lightweight cache and health tasks."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import asdict, dataclass
from datetime import UTC, datetime

from app.core.config import settings
from app.services.notifications.delivery import AlertDeliveryService
from app.services.search.workspace import SearchWorkspaceService
from app.services.storage.background_cache import BackgroundPaperCache

logger = logging.getLogger("resora.worker")


@dataclass(slots=True)
class WorkerHeartbeat:
    """Represents a single worker iteration."""

    started_at: str
    cache_freshness_hours: int
    llm_provider: str
    alert_notifications: int = 0


class WorkerRunner:
    """Runs periodic background tasks without blocking API startup."""

    def __init__(self, poll_seconds: int | None = None) -> None:
        self.poll_seconds = poll_seconds or settings.worker_poll_seconds
        self.cache_service = BackgroundPaperCache()
        self.workspace_service = SearchWorkspaceService()
        self.alert_delivery = AlertDeliveryService()

    def build_heartbeat(self) -> WorkerHeartbeat:
        """Return observability-friendly heartbeat metadata."""

        return WorkerHeartbeat(
            started_at=datetime.now(UTC).isoformat(),
            cache_freshness_hours=settings.cache_freshness_hours,
            llm_provider=settings.default_llm_provider,
        )

    async def run_iteration(self) -> WorkerHeartbeat:
        """Perform one safe worker iteration."""

        heartbeat = self.build_heartbeat()
        metadata = asdict(heartbeat)
        logger.info("worker iteration started", extra={"heartbeat": metadata})
        _ = self.cache_service
        alert_run = self.workspace_service.run_alerts(user_id="anonymous")
        if alert_run.notifications:
            await self.alert_delivery.deliver(alert_run)
        heartbeat = WorkerHeartbeat(
            started_at=heartbeat.started_at,
            cache_freshness_hours=heartbeat.cache_freshness_hours,
            llm_provider=heartbeat.llm_provider,
            alert_notifications=len(alert_run.notifications),
        )
        metadata = asdict(heartbeat)
        logger.info("worker iteration completed", extra={"heartbeat": metadata})
        return heartbeat

    async def serve(self) -> None:
        """Run the worker loop until interrupted."""

        logger.info("worker loop online", extra={"poll_seconds": self.poll_seconds})
        while True:
            await self.run_iteration()
            await asyncio.sleep(self.poll_seconds)


async def _main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    runner = WorkerRunner()
    await runner.serve()


if __name__ == "__main__":
    asyncio.run(_main())
