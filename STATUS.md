# RESORA Master Status

## Verification update — 2026-10-30

- `npm run check:all`: passed (ESLint, TypeScript, 10 Playwright tests, production build, API 218 passed / 2 skipped). Existing Starlette/httpx deprecation warning remains.
- Search E2E now asserts the first result card is visible, allowing multiple correct results. The fake translation adapter test now uses a valid request fixture and the correct provider-limits protocol.
- `pytest-timeout` is installed in `apps/api/.venv` and is already declared with pytest in `apps/api/pyproject.toml` dev extras. No real model was loaded or downloaded.
- Added backend SSE search events (`source_started`, `source_results`, `source_failed`, `done`) while retaining the JSON search route. The Search UI streams source batches, deduplicates interim results by DOI/title, prefers scholarly records when titles collide, and holds translated searches until their translated final response is ready.
- After the streaming changes and final UI behavior fix, `npm run check:all` passes: 10 Playwright tests; API 218 passed / 2 skipped; production build and typecheck pass. The API keeps one Starlette/httpx deprecation warning.
- Search API presentation strips connector IDs, per-source coverage, ranking explanations, retry IDs, cache diagnostics, and raw provider exceptions from standard and streamed responses. Failure text is generic; streamed result records use a generic `research` source. Regression coverage checks SSE connector-name redaction.
- Search tests inject fake web providers, and translation workflow tests inject deterministic fake translations. `apps/api/.venv` result: 218 passed, 2 skipped; focused SSE privacy test: 1 passed. No model or pack downloads occurred.
- Prompt 1 remains **in progress**: only 16 of 36 required full UI locale catalogs are present; streamed-search latency/partial-failure/accessibility and the full requirement-by-requirement audit are outstanding; public deployment evidence is outstanding.
- Localization gate audit: `npm run i18n:check` currently fails on 70 new hardcoded English UI messages; the locale checker separately reports 30 missing full-app catalogs. The root `check:all` script does not yet include this failing localization gate, so a green root gate is not evidence that full-app localization is complete.

Source: requirements in `docs/PRODUCT_SPEC.md`. Status means implementation evidence found so far, not product completeness. -Partial- indicates some code or a screen exists but full acceptance is not yet verified. -Missing- means no complete evidence has been audited. This is the initial audit baseline; update rows as each phase is verified.

## Prompt 1 - Foundation & App Shell

| Item | Status | Code / evidence | Notes |
| --- | --- | --- | --- |
| HOME-01 | Partial | `apps/web/src/pages/HomePage.tsx` | Exists in repository; full acceptance, negative cases and source-PDF requirements need item-level test audit. |
| SRCH-01 | Partial | `apps/web/src/pages/SearchPage.tsx; apps/api/app/services/search/` | Exists in repository; full acceptance, negative cases and source-PDF requirements need item-level test audit. |
| SRCH-02 | Partial | `apps/web/src/pages/SearchPage.tsx; apps/api/app/services/search/` | Exists in repository; full acceptance, negative cases and source-PDF requirements need item-level test audit. |
| SRCH-03 | Partial | `apps/web/src/pages/SearchPage.tsx; apps/api/app/services/search/` | Exists in repository; full acceptance, negative cases and source-PDF requirements need item-level test audit. |
| SRCH-04 | Partial | `apps/web/src/pages/SearchPage.tsx; apps/api/app/services/search/` | Exists in repository; full acceptance, negative cases and source-PDF requirements need item-level test audit. |
| SRCH-05 | Partial | `apps/web/src/pages/SearchPage.tsx; apps/api/app/services/search/` | Exists in repository; full acceptance, negative cases and source-PDF requirements need item-level test audit. |
| SRCH-06 | Partial | `apps/web/src/pages/SearchPage.tsx; apps/api/app/services/search/` | Exists in repository; full acceptance, negative cases and source-PDF requirements need item-level test audit. |
| LIB-01 | Partial | `apps/web/src/pages/ControlPage.tsx; apps/api/app/services/workspace/` | Exists in repository; full acceptance, negative cases and source-PDF requirements need item-level test audit. |
| LIB-02 | Partial | `apps/web/src/pages/ControlPage.tsx; apps/api/app/services/workspace/` | Exists in repository; full acceptance, negative cases and source-PDF requirements need item-level test audit. |
| LIB-03 | Partial | `apps/web/src/pages/ControlPage.tsx; apps/api/app/services/workspace/` | Exists in repository; full acceptance, negative cases and source-PDF requirements need item-level test audit. |
| READ-01 | Partial | `apps/web/src/pages/SummariesPage.tsx; apps/api/app/services/documents/` | Exists in repository; full acceptance, negative cases and source-PDF requirements need item-level test audit. |
| READ-02 | Partial | `apps/web/src/pages/SummariesPage.tsx; apps/api/app/services/documents/` | Exists in repository; full acceptance, negative cases and source-PDF requirements need item-level test audit. |
| READ-03 | Partial | `apps/web/src/pages/SummariesPage.tsx; apps/api/app/services/documents/` | Exists in repository; full acceptance, negative cases and source-PDF requirements need item-level test audit. |
| READ-04 | Partial | `apps/web/src/pages/SummariesPage.tsx; apps/api/app/services/documents/` | Exists in repository; full acceptance, negative cases and source-PDF requirements need item-level test audit. |
| READ-05 | Partial | `apps/web/src/pages/SummariesPage.tsx; apps/api/app/services/documents/` | Exists in repository; full acceptance, negative cases and source-PDF requirements need item-level test audit. |
| COMP-01 | Partial | `apps/web/src/pages/ComparisonPage.tsx; apps/api/app/services/comparison/` | Exists in repository; full acceptance, negative cases and source-PDF requirements need item-level test audit. |
| COMP-02 | Partial | `apps/web/src/pages/ComparisonPage.tsx; apps/api/app/services/comparison/` | Exists in repository; full acceptance, negative cases and source-PDF requirements need item-level test audit. |
| COMP-03 | Partial | `apps/web/src/pages/ComparisonPage.tsx; apps/api/app/services/comparison/` | Exists in repository; full acceptance, negative cases and source-PDF requirements need item-level test audit. |
| GAPS-01 | Partial | `apps/web/src/pages/GapsPage.tsx; apps/api/app/services/gap/` | Exists in repository; full acceptance, negative cases and source-PDF requirements need item-level test audit. |
| GAPS-02 | Partial | `apps/web/src/pages/GapsPage.tsx; apps/api/app/services/gap/` | Exists in repository; full acceptance, negative cases and source-PDF requirements need item-level test audit. |
| GAPS-03 | Partial | `apps/web/src/pages/GapsPage.tsx; apps/api/app/services/gap/` | Exists in repository; full acceptance, negative cases and source-PDF requirements need item-level test audit. |
| GAPS-04 | Partial | `apps/web/src/pages/GapsPage.tsx; apps/api/app/services/gap/` | Exists in repository; full acceptance, negative cases and source-PDF requirements need item-level test audit. |
| GAPS-05 | Partial | `apps/web/src/pages/GapsPage.tsx; apps/api/app/services/gap/` | Exists in repository; full acceptance, negative cases and source-PDF requirements need item-level test audit. |
| GAPS-06 | Partial | `apps/web/src/pages/GapsPage.tsx; apps/api/app/services/gap/` | Exists in repository; full acceptance, negative cases and source-PDF requirements need item-level test audit. |
| GAPS-07 | Partial | `apps/web/src/pages/GapsPage.tsx; apps/api/app/services/gap/` | Exists in repository; full acceptance, negative cases and source-PDF requirements need item-level test audit. |
| WRITE-01 | Partial | `apps/web/src/pages/WritingLibraryPage.tsx; apps/api/app/services/writing/` | Exists in repository; full acceptance, negative cases and source-PDF requirements need item-level test audit. |
| WRITE-02 | Partial | `apps/web/src/pages/WritingLibraryPage.tsx; apps/api/app/services/writing/` | Exists in repository; full acceptance, negative cases and source-PDF requirements need item-level test audit. |
| WRITE-03 | Partial | `apps/web/src/pages/WritingLibraryPage.tsx; apps/api/app/services/writing/` | Exists in repository; full acceptance, negative cases and source-PDF requirements need item-level test audit. |
| WRITE-04 | Partial | `apps/web/src/pages/WritingLibraryPage.tsx; apps/api/app/services/writing/` | Exists in repository; full acceptance, negative cases and source-PDF requirements need item-level test audit. |
| WRITE-05 | Partial | `apps/web/src/pages/WritingLibraryPage.tsx; apps/api/app/services/writing/` | Exists in repository; full acceptance, negative cases and source-PDF requirements need item-level test audit. |
| ACCOUNT-01 | Partial | `apps/web/src/components/layout/AppShell.jsx; apps/api/app/services/security/` | Exists in repository; full acceptance, negative cases and source-PDF requirements need item-level test audit. |
| ACCOUNT-02 | Partial | `apps/web/src/components/layout/AppShell.jsx; apps/api/app/services/security/` | Exists in repository; full acceptance, negative cases and source-PDF requirements need item-level test audit. |
| ACCOUNT-03 | Partial | `apps/web/src/components/layout/AppShell.jsx; apps/api/app/services/security/` | Exists in repository; full acceptance, negative cases and source-PDF requirements need item-level test audit. |
| TEAMS-01 | Partial | `apps/web/src/pages/CollaborationPage.tsx; apps/api/app/services/workspace/` | Exists in repository; full acceptance, negative cases and source-PDF requirements need item-level test audit. |
| PLAT-01 | Partial | `apps/web/src/App.tsx; apps/api/app/main.py; apps/api/app/services/` | Exists in repository; full acceptance, negative cases and source-PDF requirements need item-level test audit. |
| PLAT-02 | Partial | `apps/web/src/App.tsx; apps/api/app/main.py; apps/api/app/services/` | Exists in repository; full acceptance, negative cases and source-PDF requirements need item-level test audit. |
| PLAT-03 | Partial | `apps/web/src/App.tsx; apps/api/app/main.py; apps/api/app/services/` | Exists in repository; full acceptance, negative cases and source-PDF requirements need item-level test audit. |
| PLAT-04 | Partial | `apps/web/src/App.tsx; apps/api/app/main.py; apps/api/app/services/` | Exists in repository; full acceptance, negative cases and source-PDF requirements need item-level test audit. |

## Prompt 1 quality gates

| Gate | Status | Evidence / blocker |
| --- | --- | --- |
| Source PDFs read | Done | Both PDFs are present under `docs/source/`; spec captures Vision 1-34 and proposal scope/objectives/use cases/risks. |
| Git baseline | Done | `.gitignore` verified; initial commit `f22d56e` excludes `.env`, local databases, `storage/`, models, and generated Playwright artifacts. |
| `pytest-timeout` / `--timeout=60` | Done | `npm run check:all` invokes the project `.venv`; current API suite passes with `--timeout=60`. The system Python outside that venv does not have the plugin. |
| Default test providers are fake-only | Partial | Existing test fixtures found; audit that all LLM, translation, search and web providers are faked and live tests are marked/skipped. |
| Failing committed-scope test | Done | Fixed in the earlier Prompt 1 follow-through; the current full API suite passes. |
| ESLint / Prettier / scripts / i18n lint | Partial | ESLint, Prettier and i18n scripts now exist; `lint` passes with zero errors, while `lint:report` still has legacy warnings and format/i18n checks are not all wired into `check:all`. |
| Root `check:all` and CI | Partial | CI workflow exists in baseline; check whether it runs the requested complete matrix. |
| Initial JS bundle <250 KB gzip | Partial | Route-level lazy loading added; current entry JS is 407.91 KB raw / 130.76 KB gzip. Heavy dependency audit and baseline gzip measurement remain. |
| Design tokens and raw-color guard | Partial | Existing Tailwind/CSS variables exist; values and component raw colors still need migration/audit. |
| Shared accessible UI primitives and global dismissal | Partial | Existing `components/common` and `components/layout`; requested unified `components/ui` library and app-wide interaction behavior not audited. |
| App shell and responsive nav | Partial | `AppShell.jsx` wraps routes; requested nav structure, feature flags, mobile nav and shell behavior need audit. |
| Language foundation | Partial | Registry has 36 entries and local persistence; 11 additions, native-name picker, honest coverage and locale formatting remain. |
| Accessibility/performance/Lighthouse | Missing | Required axe, keyboard, touch-target, reduced-motion and Lighthouse evidence not collected. |
| Screenshots/report | Partial | Earlier Search screenshots are generated artifacts and ignored; requested shell/gallery + English/Urdu RTL matrix not captured. |

## Verification

- Source extraction used PyMuPDF to read all 19 Product Vision pages and all 15 Proposal pages.
- No model or translation job was run.
- Full Prompt 1 gate is not yet complete; see `NEXT_STEPS.md` for work order.

## Prompt 1 - verified progress (2026-10-17)

- **Quality gate:** `npm run check:all` passed. Frontend ESLint (errors only), TypeScript, 8 Playwright E2E tests, production build, and API suite all passed; API: 193 passed, 2 skipped, 5 deprecation warnings. No model, translation, or live API processes were started.
- **Bundle:** initial entry is 413.88 KB raw / 131.44 KB gzip (under the 250 KB gzip target); page routes are split. UI gallery is dev-only at `/dev/ui`.
- **Design foundation (partial):** canonical light/dark token file and Tailwind mappings added; shared UI primitives and a global popover dismissal manager added; gallery covers themes/directions; E2E verifies Escape, outside click, route change, focus return and switching popovers.
- **Still partial/missing:** migrate all existing components to tokens/primitives and enforce no raw hex outside tokens; mobile app shell and full navigation/command palette/global states; add 11 requested languages and full metadata/catalog report; complete focus-trap/axe coverage and per-primitive checks; run Lighthouse and capture the requested full screenshot matrix. Do not mark Prompt 1 complete yet.
- **Known quality caveat:** `lint` passes with zero errors; `lint:report` still reports legacy warnings. CSS bundle is 46.69 KB gzip. Existing API deprecation warnings remain.

- **Language registry (partial):** added Marathi, Telugu, Gujarati, Kannada, Malayalam, Punjabi (Gurmukhi), Filipino, Hausa, Amharic, Yoruba, and Javanese to the frontend and API registries (47 languages total); Gurmukhi is distinct from Shahmukhi. New entries state UI catalogs are pending and translation availability is provider-dependent, quality Basic. Added Punjabi Gurmukhi script-detection and registry tests. Requested on-demand font loading, catalog coverage reporting, locale formatting and persisted settings remain open.

- **Mobile shell (partial):** added compact fixed bottom navigation at widths =760px for Home, Search, Library, Reader, with Compare/Gaps/Write under More. The desktop tab bar remains centered and consistent across routes. More closes on outside press, Escape, and route changes; Escape returns focus to its trigger. Added a mobile Playwright regression test.
- **Verification after shell change:** `npm run check:all` passed: lint, typecheck, 9 E2E tests, build (417.33 KB raw / 132.13 KB gzip entry), API 194 passed / 2 skipped. API emitted 5 existing deprecation warnings.

## Prompt 1B Section A - Language readiness baseline (2026-10-17)

- Added reproducible offline inventory: `scripts/language_readiness_report.py` generates `docs/LANGUAGES.md` and the UI data file `apps/web/src/i18n/language-readiness.json` from the actual registry/catalogs.
- Actual checked-in state: 47 registered languages, 16 locale JSON files (15 non-English plus `en`), 1,455 source keys; current non-English generated catalogs record M2M-100 local INT8 and native review pending.
- Actual readiness: **0 PRODUCTION / 16 BETA / 31 PLANNED**. BETA reflects catalog coverage =90%, not QA approval. No QA scores, multi-engine results translation verification, per-language font/RTL checks, or Home/Search/Compare screenshot evidence are recorded. All PRODUCTION claims are therefore withheld.
- Added the same inventory to the existing Developer AI Admin surface. Typecheck and its Playwright regression passed.
- Catalog generation was not run.

## Prompt 1B Section B - router foundation (in progress, 2026-10-17)

- Added official OpenAI-compatible transports for Gemini, Groq, Mistral and Cerebras; OpenRouter discovers the current model catalog and permits only `:free` IDs with zero listed input/output price. GitHub Models is not registered because the official service lifecycle page reports retirement.
- Added task routing configuration, weighted distribution, bounded concurrency, provider cooldowns (shared in Redis with local fallback), response validation hooks, Redis/SQLite cache for non-user prompts, streaming with failover only before the first emitted chunk, and atomic Redis RPM/TPM/RPD/TPD reservations with a 90% daily switch threshold. Provider quota reservations fail closed if Redis is missing; OpenRouter's current 50/day free-plan allowance is configurable, not embedded in provider-call logic.
- Private/user prompts bypass response caching and providers marked ineligible; default agent LLM routing now points through `AIRouter`. Groq's hosted results-translation adapter also calls the router and marks translated material as user content. Local and dedicated Azure/Google/DeepL translation adapters retain their existing provider chain, so translation is **not yet fully consolidated**; multi-agent analysis services still use deterministic/extractive implementations in several paths.
- Added redacted numeric quota-header collection, per-provider counters and latency percentiles, an authenticated `/admin/ai-router/health` endpoint, and an Admin table that fetches configured/healthy state, calls, errors, 429s, failovers, and p50/p95 latency.
- Added `docs/AI_PROVIDERS.md` with official provider policy links and honest account-specific quota/privacy notes. `scripts/check_ai_provider_keys.py` was used for tiny checks earlier in this work; Gemini, OpenRouter and Tavily succeeded; Groq was skipped because its key is absent; Exa returned HTTP 401. No key or response content is recorded here.
- Fake-provider tests cover weighted calls, 429 failover, budgets, cooldowns, cache/privacy, validation, OpenRouter paid-model blocking, streaming fallback, and header reduction.
- Verification: latest full `npm run check:all` passed: ESLint, TypeScript, 10 Playwright E2E tests (including mocked Admin provider health), production build (417.33 KB raw / 132.13 KB gzip entry), API 208 passed / 2 skipped with `--timeout=60`. Five existing Starlette/FastAPI deprecation warnings remain. The system Python lacks `pytest-timeout`, but the project `.venv` used by `check:all` has it.
- **Still incomplete for B:** complete migration of Azure/Google/DeepL/local translation plus summaries/comparison/gaps/writing to this router; periodic hosted-provider health checks; and stronger task-specific output schemas/grounding validators. This section is not committed or marked complete yet.
