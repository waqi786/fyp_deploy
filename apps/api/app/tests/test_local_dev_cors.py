from fastapi.testclient import TestClient

from app.main import app


def test_vite_fallback_port_can_call_search_api_in_development() -> None:
    client = TestClient(app)
    response = client.options(
        "/api/v1/search/",
        headers={
            "Origin": "http://127.0.0.1:5174",
            "Access-Control-Request-Method": "POST",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://127.0.0.1:5174"
