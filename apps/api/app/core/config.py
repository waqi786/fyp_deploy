import os
from dataclasses import dataclass

try:
    from pydantic_settings import BaseSettings, SettingsConfigDict

    class Settings(BaseSettings):
        app_name: str = "Resora API"
        api_version: str = "0.1.0"
        deployment_stage: str = "development"
        database_url: str = "postgresql+psycopg://resora:resora@postgres:5432/resora"
        redis_url: str = "redis://redis:6379/0"
        frontend_url: str = "http://127.0.0.1:5173"
        cors_allowed_origins: str = "http://127.0.0.1:5173,http://localhost:5173"
        openalex_base_url: str = "https://api.openalex.org"
        arxiv_base_url: str = "https://export.arxiv.org/api/query"
        core_base_url: str = "https://api.core.ac.uk/v3"
        pmc_base_url: str = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
        semantic_scholar_base_url: str = "https://api.semanticscholar.org/graph/v1"
        crossref_base_url: str = "https://api.crossref.org"
        api_contact_email: str = "support@resora.local"
        tavily_api_key: str | None = None
        exa_api_key: str | None = None
        exa_monthly_request_limit: int | None = None
        web_search_provider: str = "tavily"
        web_search_provider_order: str = "tavily,exa"
        web_search_timeout_seconds: float = 8.0
        web_search_cache_ttl_seconds: int = 86400
        web_search_max_results: int = 10
        web_search_monthly_budgets: str = '{"tavily":1000,"exa":1000}'
        unpaywall_base_url: str = "https://api.unpaywall.org/v2"
        unpaywall_email: str = "resora@example.com"
        default_llm_provider: str = "ai_router"
        default_embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"
        minio_endpoint: str = "minio:9000"
        minio_access_key: str = "resora"
        minio_secret_key: str = "resora123"
        minio_bucket: str = "resora-figures"
        websocket_history_limit: int = 50
        worker_poll_seconds: int = 30
        serpapi_api_key: str | None = None
        semantic_scholar_api_key: str | None = None
        groq_api_key: str | None = None
        gemini_api_key: str | None = None
        openrouter_api_key: str | None = None
        mistral_api_key: str | None = None
        cerebras_api_key: str | None = None
        siliconflow_api_key: str | None = None
        modelscope_token: str | None = None
        github_models_token: str | None = None
        ai_router_routes_path: str = "apps/api/app/services/ai_router/routes.json"
        ai_router_cache_ttl_seconds: int = 86400
        ai_router_cache_path: str = "storage/ai_router_cache.sqlite3"
        ai_router_free_models_only: bool = True
        ai_router_max_concurrency: int = 4
        ai_router_timeout_seconds: float = 30.0
        ai_router_provider_limits: str = '{"openrouter":{"rpd":50}}'
        ai_router_health_probe_seconds: int = 300
        deepl_api_key: str | None = None
        translation_model: str = "openai/gpt-oss-20b"
        translation_timeout_seconds: float = 8.0
        translation_admin_user_ids: str = ""
        openai_api_key: str | None = None
        supabase_url: str | None = None
        supabase_anon_key: str | None = None
        supabase_service_role_key: str | None = None
        supabase_jwt_secret: str | None = None
        sentry_dsn: str | None = None
        alert_delivery_webhook_url: str | None = None
        smtp_host: str | None = None
        smtp_port: int = 587
        smtp_username: str | None = None
        smtp_password: str | None = None
        smtp_from_email: str = "alerts@resora.local"
        cache_freshness_hours: int = 72
        final_staging_validated: bool = False
        load_test_concurrent_users: int = 0
        backup_restore_validated: bool = False
        provider_delivery_validated: bool = False

        model_config = SettingsConfigDict(
            env_file=".env",
            extra="ignore",
        )


    settings = Settings()
except Exception:
    @dataclass
    class Settings:
        app_name: str = os.getenv("APP_NAME", "Resora API")
        api_version: str = os.getenv("API_VERSION", "0.1.0")
        deployment_stage: str = os.getenv("DEPLOYMENT_STAGE", "development")
        database_url: str = os.getenv("DATABASE_URL", "postgresql+psycopg://resora:resora@postgres:5432/resora")
        redis_url: str = os.getenv("REDIS_URL", "redis://redis:6379/0")
        frontend_url: str = os.getenv("FRONTEND_URL", "http://127.0.0.1:5173")
        cors_allowed_origins: str = os.getenv("CORS_ALLOWED_ORIGINS", "http://127.0.0.1:5173,http://localhost:5173")
        openalex_base_url: str = os.getenv("OPENALEX_BASE_URL", "https://api.openalex.org")
        arxiv_base_url: str = os.getenv("ARXIV_BASE_URL", "https://export.arxiv.org/api/query")
        core_base_url: str = os.getenv("CORE_BASE_URL", "https://api.core.ac.uk/v3")
        pmc_base_url: str = os.getenv("PMC_BASE_URL", "https://eutils.ncbi.nlm.nih.gov/entrez/eutils")
        semantic_scholar_base_url: str = os.getenv("SEMANTIC_SCHOLAR_BASE_URL", "https://api.semanticscholar.org/graph/v1")
        crossref_base_url: str = os.getenv("CROSSREF_BASE_URL", "https://api.crossref.org")
        api_contact_email: str = os.getenv("API_CONTACT_EMAIL", "support@resora.local")
        tavily_api_key: str | None = os.getenv("TAVILY_API_KEY")
        exa_api_key: str | None = os.getenv("EXA_API_KEY")
        exa_monthly_request_limit: int | None = int(os.getenv("EXA_MONTHLY_REQUEST_LIMIT", "0")) or None
        web_search_provider: str = os.getenv("WEB_SEARCH_PROVIDER", "tavily")
        web_search_provider_order: str = os.getenv("WEB_SEARCH_PROVIDER_ORDER", "tavily,exa")
        web_search_timeout_seconds: float = float(os.getenv("WEB_SEARCH_TIMEOUT_SECONDS", "8"))
        web_search_cache_ttl_seconds: int = int(os.getenv("WEB_SEARCH_CACHE_TTL_SECONDS", "86400"))
        web_search_max_results: int = int(os.getenv("WEB_SEARCH_MAX_RESULTS", "10"))
        web_search_monthly_budgets: str = os.getenv("WEB_SEARCH_MONTHLY_BUDGETS", '{"tavily":1000,"exa":1000}')
        unpaywall_base_url: str = os.getenv("UNPAYWALL_BASE_URL", "https://api.unpaywall.org/v2")
        unpaywall_email: str = os.getenv("UNPAYWALL_EMAIL", "resora@example.com")
        default_llm_provider: str = os.getenv("DEFAULT_LLM_PROVIDER", "ai_router")
        default_embedding_model: str = os.getenv("DEFAULT_EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2")
        minio_endpoint: str = os.getenv("MINIO_ENDPOINT", "minio:9000")
        minio_access_key: str = os.getenv("MINIO_ACCESS_KEY", "resora")
        minio_secret_key: str = os.getenv("MINIO_SECRET_KEY", "resora123")
        minio_bucket: str = os.getenv("MINIO_BUCKET", "resora-figures")
        websocket_history_limit: int = int(os.getenv("WEBSOCKET_HISTORY_LIMIT", "50"))
        worker_poll_seconds: int = int(os.getenv("WORKER_POLL_SECONDS", "30"))
        serpapi_api_key: str | None = os.getenv("SERPAPI_API_KEY")
        semantic_scholar_api_key: str | None = os.getenv("SEMANTIC_SCHOLAR_API_KEY")
        groq_api_key: str | None = os.getenv("GROQ_API_KEY")
        gemini_api_key: str | None = os.getenv("GEMINI_API_KEY")
        openrouter_api_key: str | None = os.getenv("OPENROUTER_API_KEY")
        mistral_api_key: str | None = os.getenv("MISTRAL_API_KEY")
        cerebras_api_key: str | None = os.getenv("CEREBRAS_API_KEY")
        siliconflow_api_key: str | None = os.getenv("SILICONFLOW_API_KEY")
        modelscope_token: str | None = os.getenv("MODELSCOPE_TOKEN")
        github_models_token: str | None = os.getenv("GITHUB_MODELS_TOKEN")
        ai_router_routes_path: str = os.getenv("AI_ROUTER_ROUTES_PATH", "apps/api/app/services/ai_router/routes.json")
        ai_router_cache_ttl_seconds: int = int(os.getenv("AI_ROUTER_CACHE_TTL_SECONDS", "86400"))
        ai_router_cache_path: str = os.getenv("AI_ROUTER_CACHE_PATH", "storage/ai_router_cache.sqlite3")
        ai_router_free_models_only: bool = os.getenv("AI_ROUTER_FREE_MODELS_ONLY", "true").lower() == "true"
        ai_router_max_concurrency: int = int(os.getenv("AI_ROUTER_MAX_CONCURRENCY", "4"))
        ai_router_timeout_seconds: float = float(os.getenv("AI_ROUTER_TIMEOUT_SECONDS", "30"))
        ai_router_provider_limits: str = os.getenv("AI_ROUTER_PROVIDER_LIMITS", '{"openrouter":{"rpd":50}}')
        ai_router_health_probe_seconds: int = int(os.getenv("AI_ROUTER_HEALTH_PROBE_SECONDS", "300"))
        deepl_api_key: str | None = os.getenv("DEEPL_API_KEY")
        translation_model: str = os.getenv("TRANSLATION_MODEL", "openai/gpt-oss-20b")
        translation_timeout_seconds: float = float(os.getenv("TRANSLATION_TIMEOUT_SECONDS", "8"))
        translation_admin_user_ids: str = os.getenv("TRANSLATION_ADMIN_USER_IDS", "")
        openai_api_key: str | None = os.getenv("OPENAI_API_KEY")
        supabase_url: str | None = os.getenv("SUPABASE_URL")
        supabase_anon_key: str | None = os.getenv("SUPABASE_ANON_KEY")
        supabase_service_role_key: str | None = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
        supabase_jwt_secret: str | None = os.getenv("SUPABASE_JWT_SECRET")
        sentry_dsn: str | None = os.getenv("SENTRY_DSN")
        alert_delivery_webhook_url: str | None = os.getenv("ALERT_DELIVERY_WEBHOOK_URL")
        smtp_host: str | None = os.getenv("SMTP_HOST")
        smtp_port: int = int(os.getenv("SMTP_PORT", "587"))
        smtp_username: str | None = os.getenv("SMTP_USERNAME")
        smtp_password: str | None = os.getenv("SMTP_PASSWORD")
        smtp_from_email: str = os.getenv("SMTP_FROM_EMAIL", "alerts@resora.local")
        cache_freshness_hours: int = int(os.getenv("CACHE_FRESHNESS_HOURS", "72"))
        final_staging_validated: bool = os.getenv("FINAL_STAGING_VALIDATED", "false").lower() == "true"
        load_test_concurrent_users: int = int(os.getenv("LOAD_TEST_CONCURRENT_USERS", "0"))
        backup_restore_validated: bool = os.getenv("BACKUP_RESTORE_VALIDATED", "false").lower() == "true"
        provider_delivery_validated: bool = os.getenv("PROVIDER_DELIVERY_VALIDATED", "false").lower() == "true"


    settings = Settings()
