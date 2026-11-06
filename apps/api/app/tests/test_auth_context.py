import base64
import hashlib
import hmac
import json

from app.api.deps import get_auth_context
from app.core.config import settings


def _unsigned_jwt(payload: dict) -> str:
    header = base64.urlsafe_b64encode(json.dumps({"alg": "none"}).encode()).decode().rstrip("=")
    body = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip("=")
    return f"{header}.{body}."


def _signed_jwt(payload: dict, secret: str) -> str:
    header = base64.urlsafe_b64encode(json.dumps({"alg": "HS256"}).encode()).decode().rstrip("=")
    body = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip("=")
    signature = hmac.new(secret.encode(), f"{header}.{body}".encode(), hashlib.sha256).digest()
    encoded = base64.urlsafe_b64encode(signature).decode().rstrip("=")
    return f"{header}.{body}.{encoded}"


def test_auth_context_prefers_explicit_resora_user_header() -> None:
    context = __import__("asyncio").run(get_auth_context(x_resora_user="user-header"))
    assert context.user_id == "user-header"
    assert context.source == "x-resora-user"


def test_auth_context_reads_supabase_subject_from_bearer_token() -> None:
    token = _unsigned_jwt({"sub": "supabase-user-1"})
    context = __import__("asyncio").run(get_auth_context(authorization=f"Bearer {token}"))
    assert context.user_id == "supabase-user-1"
    assert context.source == "supabase-jwt"


def test_auth_context_verifies_hs256_when_secret_is_configured(monkeypatch) -> None:
    monkeypatch.setattr(settings, "supabase_jwt_secret", "secret")
    token = _signed_jwt({"sub": "verified-user"}, "secret")
    context = __import__("asyncio").run(get_auth_context(authorization=f"Bearer {token}"))
    assert context.user_id == "verified-user"
    assert context.verified is True


def test_auth_context_rejects_bad_signature_when_secret_is_configured(monkeypatch) -> None:
    monkeypatch.setattr(settings, "supabase_jwt_secret", "secret")
    token = _signed_jwt({"sub": "attacker"}, "wrong-secret")
    context = __import__("asyncio").run(get_auth_context(authorization=f"Bearer {token}"))
    assert context.user_id == "anonymous"
    assert context.source == "invalid-jwt"


def test_auth_context_falls_back_to_anonymous() -> None:
    context = __import__("asyncio").run(get_auth_context())
    assert context.user_id == "anonymous"
