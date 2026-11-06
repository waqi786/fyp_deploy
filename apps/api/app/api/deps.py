from __future__ import annotations

import base64
import hashlib
import hmac
import json
from dataclasses import dataclass
from typing import Annotated

from fastapi import Header

from app.core.config import settings


@dataclass(frozen=True)
class AuthContext:
    user_id: str
    source: str = "anonymous"
    verified: bool = False


def _decode_jwt_payload(token: str) -> dict:
    parts = token.split(".")
    if len(parts) < 2:
        return {}
    payload = parts[1]
    padding = "=" * (-len(payload) % 4)
    try:
        decoded = base64.urlsafe_b64decode(f"{payload}{padding}".encode("utf-8"))
        return json.loads(decoded.decode("utf-8"))
    except (ValueError, json.JSONDecodeError):
        return {}


def _b64url_decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(f"{value}{padding}".encode("utf-8"))


def _verify_hs256(token: str, secret: str) -> bool:
    parts = token.split(".")
    if len(parts) != 3:
        return False
    signing_input = f"{parts[0]}.{parts[1]}".encode("utf-8")
    try:
        expected = hmac.new(secret.encode("utf-8"), signing_input, hashlib.sha256).digest()
        supplied = _b64url_decode(parts[2])
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(expected, supplied)


async def get_auth_context(
    authorization: Annotated[str | None, Header()] = None,
    x_resora_user: Annotated[str | None, Header()] = None,
) -> AuthContext:
    if x_resora_user:
        return AuthContext(user_id=x_resora_user.strip(), source="x-resora-user", verified=False)

    if authorization and authorization.lower().startswith("bearer "):
        token = authorization.split(" ", 1)[1].strip()
        if settings.supabase_jwt_secret and not _verify_hs256(token, settings.supabase_jwt_secret):
            return AuthContext(user_id="anonymous", source="invalid-jwt", verified=False)
        payload = _decode_jwt_payload(token)
        subject = str(payload.get("sub") or payload.get("user_id") or "").strip()
        if subject:
            return AuthContext(
                user_id=subject,
                source="supabase-jwt",
                verified=bool(settings.supabase_jwt_secret),
            )

    return AuthContext(user_id="anonymous", source="anonymous", verified=False)
