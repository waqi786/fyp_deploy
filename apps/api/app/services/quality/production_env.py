from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


PLACEHOLDER_MARKERS = {
    "",
    "change-this",
    "change-this-too",
    "change-this-strong-password",
    "your-domain.example",
    "https://your-domain.example",
}


@dataclass(frozen=True)
class EnvGate:
    name: str
    passed: bool
    detail: str
    blocking: bool = True


@dataclass(frozen=True)
class EnvValidationReport:
    ready: bool
    checked_count: int
    blocking_count: int
    warning_count: int
    gates: list[EnvGate]

    def to_dict(self) -> dict:
        return {
            "ready": self.ready,
            "checked_count": self.checked_count,
            "blocking_count": self.blocking_count,
            "warning_count": self.warning_count,
            "gates": [gate.__dict__ for gate in self.gates],
        }


def parse_env_file(path: str | Path) -> dict[str, str]:
    env_path = Path(path)
    values: dict[str, str] = {}
    for line in env_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def validate_env_values(values: dict[str, str]) -> EnvValidationReport:
    gates = [
        _equals("DEPLOYMENT_STAGE", values, "production"),
        _https_public("FRONTEND_URL", values),
        _cors(values),
        _not_placeholder("DATABASE_URL", values),
        _not_placeholder("REDIS_URL", values, allow_local=False),
        _not_placeholder("MINIO_ACCESS_KEY", values),
        _not_placeholder("MINIO_SECRET_KEY", values),
        _any_present("LLM provider", values, ["GROQ_API_KEY", "OPENAI_API_KEY"]),
        _not_placeholder("SUPABASE_URL", values),
        _not_placeholder("SUPABASE_ANON_KEY", values),
        _not_placeholder("SUPABASE_SERVICE_ROLE_KEY", values),
        _not_placeholder("SUPABASE_JWT_SECRET", values),
        _not_placeholder("SENTRY_DSN", values, blocking=False),
        _alert_delivery(values),
        _flag("FINAL_STAGING_VALIDATED", values),
        _load_test(values),
        _flag("BACKUP_RESTORE_VALIDATED", values),
        _flag("PROVIDER_DELIVERY_VALIDATED", values),
    ]
    blocking_count = sum(1 for gate in gates if gate.blocking and not gate.passed)
    warning_count = sum(1 for gate in gates if not gate.blocking and not gate.passed)
    return EnvValidationReport(
        ready=blocking_count == 0,
        checked_count=len(gates),
        blocking_count=blocking_count,
        warning_count=warning_count,
        gates=gates,
    )


def validate_env_file(path: str | Path) -> EnvValidationReport:
    return validate_env_values(parse_env_file(path))


def _value(key: str, values: dict[str, str]) -> str:
    return values.get(key, "").strip()


def _is_placeholder(value: str) -> bool:
    lowered = value.lower()
    return lowered in PLACEHOLDER_MARKERS or "your-domain" in lowered or "[your-password]" in lowered


def _equals(key: str, values: dict[str, str], expected: str) -> EnvGate:
    actual = _value(key, values)
    return EnvGate(key, actual == expected, f"{key} must be {expected}; current value is {actual or 'missing'}.")


def _not_placeholder(key: str, values: dict[str, str], *, allow_local: bool = True, blocking: bool = True) -> EnvGate:
    actual = _value(key, values)
    passed = bool(actual) and not _is_placeholder(actual)
    if not allow_local and ("localhost" in actual or "127.0.0.1" in actual):
        passed = False
    return EnvGate(key, passed, f"{key} must be set to a non-placeholder production value.", blocking=blocking)


def _https_public(key: str, values: dict[str, str]) -> EnvGate:
    actual = _value(key, values)
    passed = actual.startswith("https://") and "localhost" not in actual and "127.0.0.1" not in actual and not _is_placeholder(actual)
    return EnvGate(key, passed, f"{key} must be a real HTTPS public URL; current value is {actual or 'missing'}.")


def _cors(values: dict[str, str]) -> EnvGate:
    origins = [origin.strip() for origin in _value("CORS_ALLOWED_ORIGINS", values).split(",") if origin.strip()]
    passed = bool(origins) and "*" not in origins and all(origin.startswith("https://") and "localhost" not in origin for origin in origins)
    return EnvGate("CORS_ALLOWED_ORIGINS", passed, "CORS must list explicit HTTPS production origins only.")


def _any_present(name: str, values: dict[str, str], keys: list[str]) -> EnvGate:
    passed = any(_value(key, values) and not _is_placeholder(_value(key, values)) for key in keys)
    return EnvGate(name, passed, f"At least one of {', '.join(keys)} must be configured.")


def _alert_delivery(values: dict[str, str]) -> EnvGate:
    webhook = _value("ALERT_DELIVERY_WEBHOOK_URL", values)
    smtp_ready = all(_value(key, values) for key in ["SMTP_HOST", "SMTP_USERNAME", "SMTP_PASSWORD", "SMTP_FROM_EMAIL"])
    passed = (bool(webhook) and not _is_placeholder(webhook)) or smtp_ready
    return EnvGate("alert_delivery", passed, "Configure ALERT_DELIVERY_WEBHOOK_URL or complete SMTP credentials.", blocking=False)


def _flag(key: str, values: dict[str, str]) -> EnvGate:
    actual = _value(key, values).lower()
    return EnvGate(key, actual == "true", f"{key} must be true after the real production validation step is completed.")


def _load_test(values: dict[str, str]) -> EnvGate:
    raw = _value("LOAD_TEST_CONCURRENT_USERS", values)
    try:
        users = int(raw)
    except ValueError:
        users = 0
    return EnvGate("LOAD_TEST_CONCURRENT_USERS", users >= 50, f"LOAD_TEST_CONCURRENT_USERS must be >= 50; current value is {users}.")
