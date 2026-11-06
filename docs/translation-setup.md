# Translation setup

Resora uses a key-free local chain first: reviewed Argos packs, M2M-100 418M int8, then approved OPUS-MT int8 pairs. Azure, Google Cloud, DeepL, and Groq are optional later fallbacks and are skipped when credentials are absent. Results are cached before any engine is called.

## Providers

- **Azure AI Translator:** Set `AZURE_TRANSLATOR_KEY`, `AZURE_TRANSLATOR_REGION`, and optionally `AZURE_TRANSLATOR_ENDPOINT`. The adapter batches requests using the official v3 API. Check Azure's current language list and regional service availability before enabling a language.
- **Google Cloud Translation v3:** Set `GOOGLE_TRANSLATE_PROJECT_ID` and provide Application Default Credentials to the API container. In production, use a workload identity or mount a service-account secret at `GOOGLE_APPLICATION_CREDENTIALS`; do not put the key JSON in this repository. Optional glossary: `GOOGLE_TRANSLATE_GLOSSARY_NAME`.
- **DeepL API:** Set `DEEPL_API_KEY`; unsupported language pairs are skipped automatically. A `:fx` key selects the Free endpoint.
- **Groq:** Set the existing `GROQ_API_KEY`; `TRANSLATION_MODEL` chooses the configured model.
- NLLB and LibreTranslate are not used.

## Run local translation

Create `.env` from `.env.example`, configure at least one cloud provider when available, then start the stack with `docker compose up --build`. The local service installs English-to-language and language-to-English packs listed in the official Argos package index. Requests between two non-English languages pivot through English when both model directions are installed. It is private to the Compose network and capped at 1.5 GB RAM by default. Pack inventory and license evidence appear on **Settings → Open-source notices**.

## Routing

`TRANSLATION_PROVIDER_ORDER` is a comma-separated provider list. The default order is `azure,google_cloud,deepl,groq,madlad,translator_local`. Optional `TRANSLATION_LANGUAGE_ROUTES` is JSON mapping a BCP-47 language code to a provider list, for example:

```text
TRANSLATION_LANGUAGE_ROUTES={"ur":["azure","madlad","groq"],"es":["deepl","azure","madlad","groq"]}
```

The API tries configured and pair-compatible providers in order, with `translator_local` last by default. On failure, the user receives the original paper text and a calm notice; raw provider errors are kept out of the UI. Provider health is checked at startup and every 60 seconds; admins can view health at `/admin/translation/health` and metrics at `/api/v1/search/translation/metrics`. Both require a verified JWT user whose ID is listed in `TRANSLATION_ADMIN_USER_IDS`.

## Operational limits

Redis coordinates provider request and character buckets when reachable; provider monthly/daily reservations and optional per-user daily character limits are atomic there. If Redis is unavailable, the API falls back to process-local limits. Configure provider budgets with `TRANSLATION_MONTHLY_CHARACTER_BUDGETS` and `TRANSLATION_DAILY_CHARACTER_BUDGETS` JSON maps; a provider is skipped at 90% of its cap. `TRANSLATION_USER_DAILY_CHARACTER_LIMIT` defaults to 100,000 characters per authenticated user per day. Translation misses are placed on a Redis-backed retry queue when Redis is available and exposed through an owner-scoped status endpoint; without Redis they use bounded in-process retries. Argos coverage depends on the model packs actually present in its upstream index; use the generated inventory and live health endpoint rather than assuming every configured language is installed. Translation quality and exact script coverage still require language-by-language verification.
# Local offline fallback

The Compose stack builds `translator-local` directly on Argos Translate; it does not include LibreTranslate. It requests English in both directions for configured language codes, installs only official-index packs and records installed versions and license evidence in the `argos_models` volume. First start needs network access to fetch packs. Later translation calls can run offline. Missing local pairs fall through to configured cloud/LLM providers.

Start the default stack with `docker compose up --build`. Models are stored in `argos_models`. Defaults cap the service at 1.5 GB and one CPU. Adjust `LOCAL_TRANSLATION_MEMORY_LIMIT`, `LOCAL_TRANSLATION_CPUS`, and `LOCAL_TRANSLATION_LANGUAGES` to fit the host. See [translation licenses](translation-licenses.md) before redistribution.

The API probes configured providers on startup and every 60 seconds. `/admin/translation/health` requires a verified user ID listed in `TRANSLATION_ADMIN_USER_IDS`. A provider that fails its health check is skipped until a later probe reports it healthy.

## Current key-free local chain

This section supersedes the older Argos-only setup above. From the repository root, install `apps/translator-local/requirements.txt` and CPU PyTorch for conversion, then run `python scripts/download_translation_models.py --languages ur,ar,fa,hi,zh,es,fr,de,tr,ps,sd`. Start development with `cd apps/translator-local` followed by `python -m translator_local`; the service runs one worker on `127.0.0.1:8091`. Compose mounts the ignored `models/` directory at `/models` (read-only in production).

The service checks cache in the API first, then tries Argos, M2M-100 int8, and installed OPUS-MT int8 pairs. OPUS coverage is English↔Urdu, Arabic, Persian, Hindi, Chinese, Spanish, French, German, and Turkish when the model card declares an accepted license. Missing models are skipped. Health reports each engine, loaded state, language route, and model license. Use `TRANSLATION_DISABLE_ENGINES` to exercise failover.

M2M-100 covers Resora's language IDs, but Punjabi is generated using M2M's Gurmukhi token and Traditional Chinese output is not guaranteed. Those script-specific cases need explicit validation before claiming script-level coverage. Argos packages are only eligible when their own model/data license is reviewed; the Argos Python library license is not a model license. On complete failure, Search keeps the original text with its unavailable notice.
