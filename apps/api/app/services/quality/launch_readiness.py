from app.core.config import settings
from app.schemas.quality import LaunchReadinessCheck, LaunchReadinessResponse


class LaunchReadinessService:
    def audit(self) -> LaunchReadinessResponse:
        checks: list[LaunchReadinessCheck] = []
        blocking_issues: list[str] = []
        warnings: list[str] = []

        def add_check(name: str, passed: bool, detail: str, blocking: bool = False) -> None:
            status = "ready" if passed else "needs_attention"
            checks.append(LaunchReadinessCheck(name=name, status=status, detail=detail, blocking=blocking and not passed))
            if not passed:
                if blocking:
                    blocking_issues.append(f"{name}: {detail}")
                else:
                    warnings.append(f"{name}: {detail}")

        stage_is_prod = settings.deployment_stage.lower() == "production"
        add_check(
            "deployment_stage",
            stage_is_prod,
            f"Current deployment stage is '{settings.deployment_stage}'. Use 'production' for public launch.",
            blocking=True,
        )

        cors_origins = [item.strip() for item in settings.cors_allowed_origins.split(",") if item.strip()]
        localhost_only = all("localhost" in origin or "127.0.0.1" in origin for origin in cors_origins)
        add_check(
            "cors_policy",
            not localhost_only and "*" not in cors_origins,
            "CORS is still local-only or wildcard-like; set explicit public domains before launch.",
            blocking=True,
        )

        frontend_public = settings.frontend_url.startswith("https://") and "localhost" not in settings.frontend_url and "127.0.0.1" not in settings.frontend_url
        add_check(
            "public_frontend_url",
            frontend_public,
            f"Frontend URL is '{settings.frontend_url}'. A real HTTPS public domain is required for global SaaS launch.",
            blocking=True,
        )

        db_hardened = "change-this" not in settings.database_url and "@postgres:" not in settings.database_url
        add_check(
            "database_runtime",
            db_hardened,
            "Database configuration still looks local/container-scoped. Use managed Postgres or hardened external DB.",
            blocking=True,
        )

        redis_hardened = "redis://redis:" not in settings.redis_url
        add_check(
            "redis_runtime",
            redis_hardened,
            "Redis configuration still looks container-local. Use managed Redis or hardened external Redis.",
            blocking=False,
        )

        minio_hardened = settings.minio_access_key != "resora" and settings.minio_secret_key not in {"resora123", "change-this-too"}
        add_check(
            "object_storage_secrets",
            minio_hardened,
            "Object storage credentials are still default/example values.",
            blocking=True,
        )

        provider_key_present = bool(settings.groq_api_key or settings.openai_api_key)
        add_check(
            "llm_provider_credentials",
            provider_key_present,
            "No real LLM provider key is configured yet for remote inference.",
            blocking=True,
        )

        supabase_ready = bool(
            settings.supabase_url
            and settings.supabase_anon_key
            and settings.supabase_service_role_key
            and settings.supabase_jwt_secret
        )
        add_check(
            "auth_and_rls_wiring",
            supabase_ready,
            "Supabase URL/keys/JWT secret are not fully configured, so verified auth/RLS deployment is not ready.",
            blocking=True,
        )

        alert_delivery_ready = bool(settings.alert_delivery_webhook_url or (settings.smtp_host and settings.smtp_from_email))
        add_check(
            "saved_search_alert_delivery",
            alert_delivery_ready,
            "No webhook or SMTP provider is configured for saved-search alert delivery.",
            blocking=False,
        )

        observability_ready = bool(settings.sentry_dsn)
        add_check(
            "observability",
            observability_ready,
            "Sentry DSN is not configured; production alerting/monitoring is incomplete.",
            blocking=False,
        )

        staging_ready = settings.final_staging_validated and settings.load_test_concurrent_users >= 50
        add_check(
            "final_staging_validation",
            staging_ready,
            (
                f"FINAL_STAGING_VALIDATED={settings.final_staging_validated}; "
                f"LOAD_TEST_CONCURRENT_USERS={settings.load_test_concurrent_users}. "
                "Run public staging smoke tests and 50+ concurrent-user validation before launch."
            ),
            blocking=True,
        )
        platform_gap_closed = staging_ready and settings.provider_delivery_validated and settings.backup_restore_validated
        add_check(
            "known_platform_gap",
            platform_gap_closed,
            (
                f"Provider delivery validated={settings.provider_delivery_validated}; "
                f"backup restore validated={settings.backup_restore_validated}. "
                "Final public-launch gate requires staging smoke tests, signed auth verification, provider delivery checks, backup restore, and 50+ user validation."
            ),
            blocking=True,
        )

        required_user_inputs = [
            "Public production domain name and HTTPS/TLS plan",
            "Real LLM provider key (Groq preferred, or OpenAI fallback)",
            "Supabase project URL, anon key, and service-role key",
            "Production Postgres and Redis connection URLs",
            "Production object storage credentials/bucket details",
            "Sentry DSN or monitoring provider credentials",
            "SMTP or webhook delivery credentials for saved-search alerts",
            "FINAL_STAGING_VALIDATED=true after live staging smoke test",
            "LOAD_TEST_CONCURRENT_USERS=50 or higher after a real load test",
            "BACKUP_RESTORE_VALIDATED=true after restore drill",
            "PROVIDER_DELIVERY_VALIDATED=true after auth/webhook/email/provider checks",
        ]

        recommended_next_steps = [
            "Replace example/local env values with production secrets.",
            "Wire real auth, storage, and provider credentials into the runtime.",
            "Run end-to-end staging deployment plus 50+ concurrent-user validation.",
            "Verify signed Supabase JWT auth and alert delivery in staging.",
        ]

        return LaunchReadinessResponse(
            overall_ready=len(blocking_issues) == 0,
            release_stage="public_launch" if len(blocking_issues) == 0 else "private_beta_only",
            checks=checks,
            blocking_issues=blocking_issues,
            warnings=warnings,
            required_user_inputs=required_user_inputs,
            recommended_next_steps=recommended_next_steps,
        )
