from fastapi.testclient import TestClient

from app.main import app


def test_service_health_and_readiness_endpoints_exist() -> None:
    client = TestClient(app)

    health = client.get("/health")
    assert health.status_code == 200
    assert health.json()["status"] == "healthy"

    ready = client.get("/ready")
    assert ready.status_code == 200
    assert ready.json()["status"] in {"ready", "degraded"}

    metrics = client.get("/metrics")
    assert metrics.status_code == 200
    assert metrics.headers["content-type"].startswith("text/plain")
