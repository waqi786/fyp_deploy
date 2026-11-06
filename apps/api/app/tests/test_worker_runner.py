import asyncio

from app.services.storage.background_cache import BackgroundPaperCache
from app.workers.runner import WorkerRunner


def test_worker_heartbeat_uses_runtime_settings() -> None:
    runner = WorkerRunner(poll_seconds=1)

    heartbeat = runner.build_heartbeat()

    assert heartbeat.cache_freshness_hours > 0
    assert heartbeat.llm_provider
    assert heartbeat.started_at
    assert isinstance(runner.cache_service, BackgroundPaperCache)


def test_worker_iteration_runs_alert_pipeline() -> None:
    runner = WorkerRunner(poll_seconds=1)
    heartbeat = asyncio.run(runner.run_iteration())
    assert heartbeat.alert_notifications >= 0
