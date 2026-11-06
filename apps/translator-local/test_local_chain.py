from fastapi.testclient import TestClient

import app as translator_app


client = TestClient(translator_app.app)


def setup_function() -> None:
    translator_app.TRANSLATION_LOCK.acquire()
    translator_app.TRANSLATION_LOCK.release()


def _states():
    return {
        "argos": {"status": "available", "pairs": ["en->ur"]},
        "m2m100": {"status": "available", "pairs": []},
        "opus_mt": {"status": "available", "pairs": ["en->ur"]},
    }


def test_local_engines_fail_over_in_configured_order(monkeypatch):
    calls = []

    def translate(engine, texts, source, target):
        calls.append(engine)
        if engine != "opus_mt":
            raise RuntimeError("model fixture failure")
        return ["Urdu "]

    monkeypatch.setattr(translator_app, "engine_status", _states)
    monkeypatch.setattr(translator_app, "translate_batch_with_engine", translate)
    monkeypatch.setenv("LOCAL_TRANSLATION_ENGINE_ORDER", "argos,m2m100,opus_mt")
    monkeypatch.delenv("TRANSLATION_DISABLE_ENGINES", raising=False)
    response = client.post("/translate", json={"segments": ["Hello RESORATOKENX0XEND"], "source_language": "en", "target_language": "ur"})
    assert response.status_code == 200
    assert calls == ["argos", "m2m100", "opus_mt"]
    assert response.json()["engines_used"] == ["opus_mt"]


def test_protected_tokens_are_restored_and_bad_output_uses_next_engine(monkeypatch):
    calls = []

    def translate(engine, texts, source, target):
        calls.append(engine)
        return [""] if engine == "argos" else ["Urdu "]

    monkeypatch.setattr(translator_app, "engine_status", _states)
    monkeypatch.setattr(translator_app, "translate_batch_with_engine", translate)
    monkeypatch.setenv("LOCAL_TRANSLATION_ENGINE_ORDER", "argos,m2m100,opus_mt")
    monkeypatch.delenv("TRANSLATION_DISABLE_ENGINES", raising=False)
    response = client.post("/translate", json={"segments": ["Hello RESORATOKENX0XEND"], "source_language": "en", "target_language": "ur"})
    assert response.status_code == 200
    assert calls == ["argos", "m2m100"]
    assert response.json()["engines_used"] == ["m2m100"]


def test_all_engines_disabled_returns_serviceable_unavailable_response(monkeypatch):
    monkeypatch.setattr(translator_app, "engine_status", lambda: {name: {"status": "disabled", "pairs": []} for name in ("argos", "m2m100", "opus_mt")})
    monkeypatch.setenv("TRANSLATION_DISABLE_ENGINES", "argos,m2m100,opus_mt")
    response = client.post("/translate", json={"segments": ["Hello"], "source_language": "en", "target_language": "ur"})
    assert response.status_code == 503
    assert response.json()["detail"]["message"] == "Local translation is temporarily unavailable"


def test_health_reports_engines_individually(monkeypatch):
    monkeypatch.setattr(translator_app, "engine_status", _states)
    response = client.get("/health")
    assert response.status_code == 200
    assert set(response.json()["engines"]) == {"argos", "m2m100", "opus_mt"}
