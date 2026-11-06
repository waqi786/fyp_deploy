# RESORA translation and search production work

Last checked: 2026-10-16

## Completed in this work session

- Removed the LibreTranslate runtime image from the default Compose stack. The local fallback is a small FastAPI service calling Argos Translate directly.
- Added an Argos model installer with official-index/host checks, model-version inventory, upstream license evidence, CPU settings and a 1.5 GB default memory cap.
- Added local translator health, language inventory, batch translation and a public license inventory endpoint; added an in-app **Open-source notices** page.
- Added Redis-backed shared provider request/character token buckets, provider circuit cooldowns, a shared translation cache, and monthly/daily provider-budget checks at 90%. Admin translation health includes budget use.
- Made the local provider check actual installed source/target paths (direct or via English), and changed health checks so they do not assume Spanish is installed.
- Added `--provider-order translator_local` support to `scripts/verify_translation.py` and corrected its provider-success reporting.
- Corrected stale translation setup docs and updated the Compose production stack to include Redis and the Argos service.

## Verification completed

- API tests: **162 passed, 2 skipped**. Five existing FastAPI/Starlette deprecation warnings remain.
- Frontend typecheck: passed.
- Frontend production build: passed; Vite reports the main JS chunk is about 994 kB and recommends code splitting.
- `docker compose -f docker-compose.yml config --quiet`: passed.
- `docker compose -f docker-compose.prod.yml config --quiet`: passed.
- Python syntax compilation for the local Argos service and translation verifier: passed.

## Exact blockers and remaining work

### Phase 1 — translation and model-license validation (Partial)

- The current workspace has no `.env`; checks confirmed `AZURE_TRANSLATOR_KEY`, `AZURE_TRANSLATOR_REGION`, and `GROQ_API_KEY` are absent. The API cannot verify the claimed configured cloud chain until a real local `.env` is present.
- Docker CLI is installed but the Docker Desktop Linux engine pipe is missing. The containers cannot start, so installed Argos packs, health responses and live translation cannot be verified here.
- Run `docker compose up --build api translator-local redis`, then check authenticated `/admin/translation/health` and run:
  - `python scripts/verify_translation.py`
  - `python scripts/verify_translation.py --provider-order translator_local`
- Confirm every installed Argos pack license against its individual upstream package/source license before commercial redistribution. The index currently has no per-pack license metadata; the inventory records the upstream maintainer's blanket statement rather than pretending the index supplies per-pack licenses. Exclude any pack whose license cannot be substantiated.
- Validate local-only coverage for every language the service claims; maintain the resulting exact coverage list in `docs/translation-licenses.md`.

### Phase 2 — distributed quotas and background translation (Partial)

- Provider rate buckets, cache, cooldown circuits and provider daily/monthly caps use Redis when reachable; in-memory/SQLite fallback remains for outages.
- Make monthly/daily budget reservations atomic with Redis Lua (current read/check/increment sequence can race at the 90% threshold).
- Implement per-user daily character limits and propagate the authenticated user ID into translation calls.
- Implement Redis single-flight locks across API replicas; current in-flight deduplication is process-local.
- Add durable background retry jobs and authenticated status polling/push updates in the client. No retry queue/status API is currently implemented.
- Run the requested mocked 200 requests/60 seconds test and report errors/latencies.

### Phase 3 — static UI localization and RTL (Missing/Partial)

- `App.tsx` currently exposes only six language choices and `AutoTranslator.tsx` is a runtime heuristic translator. Replace it with build-time catalogs for all 36 supported UI locales; extract visible text, labels, toasts and errors; add an ICU-aware placeholder-safe catalog generation tool and a CI hardcoded-string check.
- Persist the selected locale per user, use locale-aware dates/numbers, add fonts and logical CSS, and fully test RTL for Urdu, Arabic, Persian, Hebrew, Pashto, Sindhi and Punjabi-Arabic.
- Generate and review actual language catalogs. Do not claim that English fallback is translated content.

### Phase 4 — streamed federated search (Missing)

- Add the requested SSE endpoint/events (`source_started`, `source_results`, `source_failed`, `done`), incremental dedup/ranking and partial-failure states; connect the search UI.
- Measure first-result p95 under 2.5 seconds and merged-result p95 under 6 seconds using repeatable tests.

### Phase 5 — Prompt 1 search acceptance matrix (Needs audit)

- Audit every row of the earlier Prompt 1 status matrix against implementation and tests. Confirm source adapters, timeout/retry/limiter/circuit/cache behavior, persistent paper refresh, parser/routing, dedup/preprint linkage/provenance, facets, ranking explanations, user-language research workflow, saved/history behavior, credits and edge cases. Mark each row Done only with code and test evidence.

### Phase 6 — release verification (Missing)

- Run all API/web tests, lint, typecheck and production builds.
- Install/use Playwright and add the end-to-end flow: Urdu RTL UI → Urdu search → streamed results → translate a result → switch to Chinese.
- Capture the requested English, Urdu, Arabic, Simplified Chinese, Spanish and German screenshots.
- Repeat the 200-request load test and publish measured latency/first-result/error counts.
- Do not report **PROMPT 1 COMPLETE** until all acceptance rows above are done and verified.

## Repository state

The repository is available through Git in the current workspace. Prompt 1B Section A is committed; Section B changes are still in progress and intentionally remain uncommitted until its stated acceptance criteria are complete.

## 2026-10-30 continuation verification

- Installed `pytest-timeout` into `apps/api/.venv`. `apps/api/pyproject.toml` already declares both `pytest` and `pytest-timeout` in the `dev` optional dependencies, so no duplicate requirements file is needed.
- Fixed a malformed JSON string in the fake translation adapter test and aligned its fake provider limits with the production protocol.
- Fixed the Search visual E2E assertion to accept multiple valid result cards instead of requiring a unique locator.
- Full `npm run check:all` passes: lint, TypeScript, 10/10 Playwright E2E, production build, API 216 passed / 2 skipped. The API emits one existing Starlette/httpx deprecation warning. No real translation engines/models were invoked.
- Added Search SSE batches (`source_started`, `source_results`, `source_failed`, `done`) while preserving the JSON endpoint. The Search page consumes streamed batches, deduplicates by DOI/title while preferring scholarly records for duplicate titles, and waits for final results when translation is enabled so untranslated text does not flash. Fake-only API/E2E coverage passes; full gate: 10/10 Playwright, API 218 passed / 2 skipped.
- Still open: complete 36-language UI catalogs (only 16 locale JSON files are checked in, with 1,455 English source keys); streamed-search latency/partial-failure/accessibility audit; and the detailed item-level Prompt 1 audit. Do not mark Prompt 1 complete. Public deployment remains blocked on owner infrastructure, domain/TLS, production secrets and scale/restore evidence; see `docs/production-deployment.md`.
- Localization audit detail: `npm run i18n:check` reports 70 newly detected hardcoded English messages; `node scripts/check-ui-catalogs.mjs` reports 30 missing full-app locale files. `npm run check:all` currently omits this red gate; address strings/catalogs and make the gate honest before wiring it into the root command.


## Search fixes in progress (2026-10-17)

Completed this pass: outside-click/Escape dismissal for Search filters and results-language menu; results-language selection now enables translation and re-runs the active query; unmapped mixed-script queries use the cached translation chain before English scholarly search while retaining the original-language parallel fallback; visible result titles/snippets translate through the existing batch/cache service; result cards use compact accessible actions and brand tokens; Save posts to the existing Library endpoint; added fake-only backend tests, mocked Playwright checks, screenshots, and `STATUS.md`. PyMuPDF extraction was already present and remains in use.

Verification: 29 targeted API tests passed (one legacy fallback test excluded); 3 Search Playwright tests passed; frontend typecheck/build passed. The full API suite stops on the pre-existing default-source-list assertion in `app/tests/test_committed_scope.py`; `--timeout=60` is unavailable because `pytest-timeout` is not installed.

Remaining: obtain the Resora Product Vision and FYP Proposal PDFs for the required section/objective audit; run and fix the remaining full-suite failures; validate real translation-provider health without starting a model job; continue the remaining Search specification and then the next product phases. PyMuPDF is dual-licensed under AGPL or a commercial license; resolve the commercial licensing path before a commercial launch.


## Prompt 1 foundation follow-through (2026-10-17)

- Read both source PDFs; `docs/PRODUCT_SPEC.md` now records stable feature IDs and `docs/ROADMAP.md` maps each ID to one of the 12 prompts.
- Initialized Git and created the explicitly requested baseline commit `f22d56e` after adding ignore rules and checking that `.env`, runtime data, models, databases, and generated Playwright artifacts were excluded.
- Completed next: installed/verified timeout support; fixed the stale committed-scope source expectation; added ESLint/Prettier tooling, frontend scripts, root check:all, CI quality job and route-level lazy loading. Current bundle entry: 407.91 KB raw / 130.76 KB gzip. The API suite now passes (193 passed, 2 skipped) with the default live-test exclusion. Continue with the complete feature audit, shared UI primitives and global dismissal, shell/mobile nav, localization, accessibility, and heavy-library splitting.
- Current limitation: no claim that Prompt 1 is complete; status rows remain Partial/Missing until acceptance evidence is collected.

## Prompt 1 - next verified work

Latest `npm run check:all`: passed (lint, typecheck, 8 Playwright E2E tests, production build, API 193 passed / 2 skipped). Current entry bundle is 413.88 KB raw / 131.44 KB gzip. Shared design tokens, reusable UI primitives, global popover dismissal and the dev UI gallery are implemented as a partial foundation.

Next: finish token/primitives migration and raw-color guard; build responsive desktop/mobile shell, command palette and global state hosts; extend language metadata with the 11 requested languages (catalog generation must remain manual and is not run here); add accessibility acceptance/axe checks, complete screenshot matrix and Lighthouse audit. Keep Prompt 1 in progress until each requirement has evidence.

Language registry progress: the requested 11 languages are registered in frontend and API (47 total), including separate Punjabi Gurmukhi/Shahmukhi entries. Their UI catalogs remain pending and translation quality is marked Basic/provider-dependent. The complete check:all passed after the change: 8 browser tests, build, and API 194 passed / 2 skipped. Next language work is requested-script font loading, suggested-language picker grouping, admin catalog coverage, and persisted language preferences.

Mobile shell progress: bottom tabs are implemented and tested at 390px, with More navigation for Compare/Gaps/Write. Full check:all passed (9 E2E, API 194 passed / 2 skipped). Remaining shell requirements include command palette, notifications/credits/avatar actions, feature-flag hiding, route error/retry/report state, global offline/session/toast/progress states, and full route screenshots.

## Prompt 1B Section A - completed

`docs/LANGUAGES.md` and the Admin localization audit now report the checked-in registry/catalog state. Rebuild with `python scripts/language_readiness_report.py`. Current counts: 47 languages, 16 catalog files including English, 0 PRODUCTION / 16 BETA / 31 PLANNED. M2M-100 is the recorded catalog engine; native QA and result-translation verification remain unverified. No catalog/model generation was run.

Next: Section B multi-provider router. Do not call a language production-ready until its QA, multiple result engines, fonts/direction, and requested screenshots have real verification evidence.

## Prompt 1B current next steps

Section B router foundation exists and full `npm run check:all` passes (10 Playwright tests; API 208 passed, 2 skipped, `--timeout=60`). Before committing B, consolidate Azure/Google/DeepL/local translation and remaining AI task paths, add periodic provider health probes and task-specific schema/grounding validators. Redis-shared configured quotas/circuits and the authenticated Admin health table are now implemented. Existing direct/local translation providers must remain fake in tests. Never print or commit `.env` values; `.env` is ignored.

Then proceed in prompt order: C UI catalog quality scripts and tiny dry run only; D settings/fonts/locale/palette/global states/tokens/deprecation work; E item-level audit; F accessibility/Lighthouse/screenshots. Keep Prompt 1 open until B, D, E and F all have verified evidence. Existing B documentation notes provider quota policies and the current live key smoke outcomes.
