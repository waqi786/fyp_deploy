from app.services.quality.production_env import validate_env_values


def production_env(**overrides: str) -> dict[str, str]:
    values = {
        "DEPLOYMENT_STAGE": "production",
        "FRONTEND_URL": "https://resora.example",
        "CORS_ALLOWED_ORIGINS": "https://resora.example,https://www.resora.example",
        "DATABASE_URL": "postgresql+psycopg://resora:strong-password@db.example:5432/resora",
        "REDIS_URL": "rediss://default:secret@redis.example:6379",
        "MINIO_ACCESS_KEY": "resora-prod-access",
        "MINIO_SECRET_KEY": "resora-prod-secret",
        "GROQ_API_KEY": "gsk_live_key",
        "SUPABASE_URL": "https://project.supabase.co",
        "SUPABASE_ANON_KEY": "sb_publishable_key",
        "SUPABASE_SERVICE_ROLE_KEY": "sb_secret_key",
        "SUPABASE_JWT_SECRET": "jwt-secret",
        "SENTRY_DSN": "https://public@sentry.example/1",
        "ALERT_DELIVERY_WEBHOOK_URL": "https://hooks.example/resora",
        "FINAL_STAGING_VALIDATED": "true",
        "LOAD_TEST_CONCURRENT_USERS": "50",
        "BACKUP_RESTORE_VALIDATED": "true",
        "PROVIDER_DELIVERY_VALIDATED": "true",
    }
    values.update(overrides)
    return values


def test_production_env_validator_passes_complete_env() -> None:
    report = validate_env_values(production_env())
    assert report.ready is True
    assert report.blocking_count == 0
    assert report.checked_count >= 18


def test_production_env_validator_blocks_placeholders_and_missing_load_test() -> None:
    report = validate_env_values(
        production_env(
            FRONTEND_URL="https://your-domain.example",
            GROQ_API_KEY="",
            LOAD_TEST_CONCURRENT_USERS="0",
        )
    )
    assert report.ready is False
    assert report.blocking_count >= 3
    failed = {gate.name for gate in report.gates if not gate.passed}
    assert "FRONTEND_URL" in failed
    assert "LLM provider" in failed
    assert "LOAD_TEST_CONCURRENT_USERS" in failed
