# AI providers and routing policy

Checked against official provider documentation on **2026-10-17**. Provider quotas and free offers change; we intentionally do not hard-code RPM/TPM/RPD/TPD values that providers assign per account, project, model or tier. The router records numeric remaining-request/token headers when a provider returns them. Operators must review the linked live quota pages before production rollout.

## Provider matrix

| Provider | Adapter / model source | Current free limits | Free input used for training? | Commercial terms / private content | Status |
| --- | --- | --- | --- | --- | --- |
| Google Gemini Developer API | OpenAI-compatible API; `gemini-3.8-flash` | Project/model/tier-specific; check AI Studio. No stable universal RPM/TPM/RPD/TPD values. | Free-tier input may be used to improve products; paid-tier data use differs. | Private/user content is blocked by router policy. | Tiny live request succeeded using `gemini-3.8-flash`. |
| OpenRouter | Official `/models` catalog; router selects only `:free` IDs with zero prompt and completion prices; Qwen-only dynamic pool is separate | Free plan: 50 requests/day and 20/minute; after buying $10 credits the daily allowance rises to 1,000. Per-model provider limits may be lower. | OpenRouter does not train on inputs; upstream providers may retain or train depending on each model/provider. | Private/user content blocked; review selected model/provider terms. | Tiny live request succeeded. Current live catalog check returned no Qwen `:free` IDs, so the Qwen pool correctly stays empty and generic free models remain fallback. |
| Groq | OpenAI-compatible API; active route `openai/gpt-oss-20b` | Organization/model-specific; inspect console and response rate-limit headers. | Review current Groq data controls for the account. | User content is permitted by current router configuration but confirm retention/account terms before launch. | Tiny live request succeeded with the active model. |
| SiliconFlow | OpenAI-compatible; activated only when `SILICONFLOW_API_KEY` is set | Account/model-specific; no assumed universal free quota. | Review account-specific privacy and data controls. | Disabled for user content by default. | Optional; key absent. |
| ModelScope | OpenAI-compatible; activated only when `MODELSCOPE_TOKEN` is set | Account/model-specific; no assumed universal free quota. | Review service and selected model terms before sending data. | Disabled for user content by default. | Optional; key absent. |
| Mistral | OpenAI-compatible API | Workspace/model/plan-specific; no stable universal quota. | Training preferences and retention are separate controls; do not assume ZDR on free tier. | Disabled for user content until an operator reviews and configures acceptable privacy settings. No key configured. | Adapter skips when key is absent. |
| Cerebras | OpenAI-compatible API | Plan/model-specific; published free tier has lower rate limits, exact active quota is account-specific. | Not approved for private content by this project pending documented review. | No key configured; adapter skips automatically. | Disabled. |
| GitHub Models | — | — | — | The service was retired on July 30, 2026 according to GitHub's official docs. | Not registered; credential placeholder remains only for migration compatibility. |
| Azure AI Translator, Google Cloud Translation, DeepL | Existing official translation adapters | Account/plan-specific. | Governed by each configured account and plan. | Their existing adapter path has not yet been consolidated into the AI Router. Confirm enterprise/privacy configuration before sending private text. | Optional; no keys are assumed. |
| Argos, M2M-100, OPUS-MT | Local translation service | Local resource limits only | Local processing | Suitable for content that must remain local; quality/coverage varies by installed engine and language pair. | Existing local translation chain remains available where installed. |

Sources: [Gemini pricing and data use](https://ai.google.dev/gemini-api/docs/pricing), [Gemini rate limits](https://ai.google.dev/gemini-api/docs/rate-limits), [Gemini OpenAI compatibility](https://ai.google.dev/gemini-api/docs/openai), [OpenRouter models API](https://openrouter.ai/docs/api/api-reference/models/get-models), [OpenRouter pricing](https://openrouter.ai/pricing/), [Groq rate limits](https://console.groq.com/docs/rate-limits), [Groq data controls](https://console.groq.com/docs/your-data), [Mistral usage limits](https://docs.mistral.ai/admin/billing-usage/usage-limits), [Mistral zero data retention](https://docs.mistral.ai/admin/monitor-comply/zero-data-retention), [Cerebras pricing](https://inference-docs.cerebras.ai/support/pricing), [GitHub Models lifecycle](https://docs.github.com/en/github-models).

## Privacy and routing rules

- Missing credentials make providers unavailable; no adapter falls back to a made-up endpoint.
- Hosted providers marked `allow_user_content=false` cannot receive uploaded PDFs, private notes, unpublished drafts or chat. Gemini free and OpenRouter are blocked for those requests. User-content responses are not stored in Redis or the local SQLite response cache.
- OpenRouter model discovery accepts only model IDs ending in `:free` and explicit zero input/output price. Do not remove this guard or disable `AI_ROUTER_FREE_MODELS_ONLY` in production without a reviewed billing control.
- API payloads and provider exception bodies are not logged. The router keeps provider/task counters and numeric rate-limit telemetry only.
- The existing translation chain has its own official/local adapters, language routing, quotas, cache and provider fallback. Full consolidation into this router remains a migration item; do not claim every translation path already routes through `AIRouter`.
- Configured RPM/TPM/RPD/TPD reservations use atomic Redis counters shared across workers and reject the provider when the shared quota cannot be reached/enforced. Provider response remaining-request/token headers update short-lived shared reservations. Without Redis, providers with an explicit shared quota are skipped. Route-level `daily_request_limit` and cooldown state still have process-local fallback behavior; periodic hosted-provider health probes remain a deployment requirement.
- Asian-language translation routes add weight to the dynamically discovered Qwen `:free` pool for zh-Hans, zh-Hant, ja, ko, vi, th, id, ms, and fil. The judge pool prefers the largest discovered free Qwen model; all candidates remain zero-priced `:free` entries.
- SiliconFlow uses `https://api.siliconflow.com/v1`; ModelScope uses `https://api-inference.modelscope.cn/v1`. They are not enabled without their keys and are blocked from user/private content unless policy is reviewed. These endpoints and account terms must be validated against the current official service docs before enabling.

Configure additional provider ceilings with `AI_ROUTER_PROVIDER_LIMITS`, for example `{"openrouter":{"rpd":50},"groq":{"rpm":30,"tpm":6000,"rpd":1000,"tpd":100000}}`. Only enter limits verified in the provider console/docs for the actual account and model.

## Optional keys to add

| Key | Signup / console | Why add it |
| --- | --- | --- |
| `GROQ_API_KEY` | [Groq Console](https://console.groq.com/keys) | Another inference pool; current quota is model and organization specific. Review Groq's data controls and service agreement. |
| `MISTRAL_API_KEY` | [Mistral Console](https://console.mistral.ai/) | Additional multilingual models. Free availability, training settings and ZDR eligibility vary; review the applicable terms before enabling private content. |
| `CEREBRAS_API_KEY` | [Cerebras Cloud](https://cloud.cerebras.ai/) | Additional inference pool; free tier is rate-limited and exact limits depend on the account. Private-content use remains disabled pending review. |
| `SILICONFLOW_API_KEY` | [SiliconFlow](https://docs.siliconflow.com/) | Optional OpenAI-compatible model pool; verify the account's privacy, region and quota terms first. |
| `MODELSCOPE_TOKEN` | [ModelScope](https://modelscope.cn/) | Optional OpenAI-compatible model pool; verify token scope, selected model license and quota first. |
| `GITHUB_MODELS_TOKEN` | None currently | GitHub Models was retired July 30, 2026; this key will not enable a provider. |

Do not add production secrets to `.env.example` or `.env.production.example`. Put credentials only in an ignored local `.env` or deployment secret manager.

## Smoke-test script

`python scripts/check_ai_provider_keys.py --providers gemini,openrouter,groq` sends a short generic prompt and prints provider/model/status/latency only. It does not print response bodies or credentials. Run live smoke checks manually; normal tests must use fake providers.
