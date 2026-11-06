# Resora Implementation Status

This repository now contains more than a visual scaffold, but it is still not the full 400+ feature product.

## Implemented in code

- Versioned FastAPI app with routes for health, search, chat, summaries, graph analysis, and workspaces.
- Versioned FastAPI app with routes for health, search, chat, summaries, graph analysis, comparison, trust analysis, exports, and workspaces.
- Per-source service modules for OpenAlex, arXiv, Crossref, and Unpaywall.
- Per-source service modules for OpenAlex, arXiv, CORE, PMC, Semantic Scholar, Google Scholar, Crossref, and Unpaywall.
- Exact baseline deduplication logic with tests.
- Third-tier semantic deduplication fallback now merges near-duplicate records beyond DOI and normalized-title matches, with tests.
- Deterministic chunking and chunk ID generation.
- In-memory hybrid retrieval with BM25, dense cosine scoring, and weighted reciprocal-rank fusion.
- Grounded chat flow that returns citations, confidence scores, source spans, and multimodal retrieval mode when figures/tables/equations are provided.
- Model-provider abstraction plus tiered summarization with bullet summary, structured sections, equations, and Urdu parallel output.
- PDF extraction service with blocked-domain detection, arXiv redirect handling, reference stripping, equation detection, caption-based figure extraction, and OCR-style fallback boundary.
- Draft generation service that combines extracted text and figure analysis into six sections with self-critique.
- Literature-review writing service with 10-section outlining, export packages, self-critique, cover-letter generation, and peer-review response drafting.
- Citation graph metric service with influence score, PageRank, citation velocity, and bridge-node detection.
- Draft self-critique service for supported versus unsupported claims.
- Multi-paper comparison engine with similarity scoring, contradiction hints, leaderboard ranking, and markdown export.
- Trust-analysis service with heuristic trust score, novelty score, evidence strength, and signal extraction.
- Citation export service for BibTeX, RIS, and CSL-JSON.
- Citation library service with duplicate grouping, unread queue defaults, and live citation-style previews.
- Workspace RBAC detail model and expanded schema for members, comparisons, annotations, gap reports, exports, and audit logs.
- Collaboration service slice for activity feeds, team dashboards, digests, guest links, and AI-usage quota summaries.
- Background paper cache service with batched inserts, retry/backoff pattern, and freshness checks.
- Structured source-search contract (`SourceSearchRequest` + filters), config-driven upstream base URLs, and named source-failure reporting.
- Optional live integration tests for OpenAlex and Crossref, gated behind `RESORA_RUN_INTEGRATION=1`.
- Search API pagination metadata now includes page, total pages, returned result count, and next-page availability.
- Search responses now include cache-upsert status from the background paper cache service.
- Synthetic load-test helper now verifies federated search behavior at `50` concurrent users in local tests.
- Document extraction now has URL preflight blocking for known authwall/CAPTCHA patterns in addition to blocked domains.
- Byte-based extraction now explicitly distinguishes low-text/scanned-like payloads and reports OCR fallback confidence.
- Table extraction now preserves simple pipe/tabular structure into headers, rows, and CSV export instead of caption-only placeholders.
- arXiv source URLs are normalized toward the export/PDF path before download attempts.
- Retrieval now exposes public BM25-only and dense-only rankers alongside hybrid fusion for benchmark comparison.
- Hybrid indexing verification now checks deterministic expected chunk IDs, not only chunk counts.
- Retrieval benchmark service now measures BM25, dense, and hybrid accuracy on the same fixed corpus.
- Dense retrieval now includes lightweight semantic normalization and alias expansion for paraphrase-aware local matching.
- Summary responses now carry three explicit tiers (`30_sec`, `2_min`, `5_min`) with source-span traceability.
- Summarization now records `generated_at`, `fallback_used`, `confidence_score`, and `model_used` in the response contract.
- Default model provider is now config-driven through the adapter registry instead of a permanently hardcoded heuristic provider.
- Provider-failure fallback is now tested to guarantee valid structured summary output even when the model layer raises an exception.
- Chat responses now include `generated_at`, `fallback_reason`, and `session_turns` so grounded-answer state is easier to audit.
- Session cache now persists rolling turn history rather than only the latest question/answer pair.
- Chat benchmark service now compares text-only versus multimodal grounded answers on the same fixed case set.
- Retrieval mode now distinguishes pure text answers from `text+multimodal` answers instead of labeling every grounded response as multimodal.
- Comparison requests now support up to `15` papers, covering the Phase 7 goal of moving beyond the original low cap.
- Comparison responses now expose count metadata, resolved custom columns, heatmap labels, JSON export, and snapshot metadata.
- Comparison column extraction now supports result/performance, limitation, venue, year, and access signals in addition to dataset/method/sample size.
- Trust-analysis responses now expose contradiction details with supporting evidence, not only flat contradiction summaries.
- Trust scoring now returns a `score_trace` showing base versus final trust/novelty values.
- Trust signals and changelog entries now carry supporting evidence snippets for better auditability.
- Gap-analysis responses now use structured white-space entries, contradiction evidence entries, and future-work entries instead of loose dict/string-only output.
- Gap reports now include `export_json`, `trend_summary`, and `generated_at` for better downstream reuse and auditing.
- Literature-review responses now expose section-level traceability metadata, sentence-level critique traces, export artifact metadata, overall confidence scoring, and generated timestamps.
- Draft-generation responses now include confidence scoring, source spans, and generation timestamps alongside self-critique.
- Citation-library flows now support workspace-aware saves, richer unread/open-access metadata, file-oriented export artifacts, and direct BibTeX/RIS/CSL-JSON import handling.
- Collaboration responses now expose share-link metadata, task-board summaries, member presence, review checkpoints, packet contents, and generation timestamps.
- Workspace RBAC detail now includes share capabilities, collaboration modes, and activity summaries alongside permissions.
- Security/compliance responses now include refresh-token rotation posture, audit entries, note-protection metadata, signed-URL traceability, backup manifest details, compliance flags, and generation timestamps.
- Mobile/offline responses now expose offline bundles, sync manifest metadata, cache policy, push categories, device-layout hints, continuity payloads, readiness scoring, and generation timestamps.
- Developer-platform responses now expose API-key posture, structured webhook previews, plugin capability summaries, import-job metadata, richer admin dashboard stats, browser-extension routing hints, and generation timestamps.
- Advanced-intelligence responses now expose workflow trace, evidence trace, guardrail decisions, orchestration confidence, review diff detail, and generation timestamps.
- Quality APIs now expose a machine-readable launch-readiness audit, and backend CORS policy is environment-driven instead of hardcoded wildcard-only behavior.
- Extended ERD coverage for projects, authors, concepts, embeddings, citations, folders, tags, notifications, plagiarism checks, and evaluation runs while keeping `research_papers` as shared cache data instead of user-owned rows.
- Extended ERD coverage for projects, authors, concepts, embeddings, citations, annotations/highlights, notes, folders, tags, collaborators, share links, notifications, plagiarism checks, export jobs, and evaluation runs while keeping `research_papers` as shared cache data instead of user-owned rows.
- Baseline evaluation service that scores latency, dedup reduction, summary quality, RAG accuracy, citation-graph accuracy, draft success rate, and concurrent-user readiness against the documented targets.
- PWA starter assets: manifest, service worker registration, and installable shell support.
- Tailwind-ready frontend pipeline with theme switching, RTL toggle, and mobile-first shell direction.
- Personalization service slice for recommendation topics, low-bandwidth widgets, accessibility presets, and offline sync summaries.
- Analytics service slice for trend charts, methodology heatmaps, co-authorship graphs, whitespace maps, and workspace dashboards.
- Security and compliance service slice for refresh-token posture, encrypted private notes, rate-limit summaries, signed PDF URLs, GDPR actions, audit logging, and prompt-injection sanitization.
- Mobile and offline service slice for installable PWA flows, cached reading plans, swipe triage, background sync summaries, and QR share payloads.
- Developer platform slice for public REST and GraphQL access, API-key issuance, browser-extension intake, plugin registry, prompt templates, bulk reference import, CLI automation, and admin usage dashboards.
- Advanced intelligence slice for multi-agent coordination, adaptive retrieval depth, cross-lingual evidence marking, debate mode, explainable ranking, review-update diffs, benchmark-aware reasoning, and hallucination omission guardrails.
- Formal multi-agent architecture now includes a planner, search agent, reading/extraction agent, comparison agent, critique/trust agent, gap agent, writing agent, and citation agent with per-agent prompt templates, typed schemas, and a lightweight state-machine orchestrator.
- Non-functional quality slice now includes sentence-level traceability checks, stronger beat-the-baseline quality gates, free-tier posture checks, OpenAPI documentation notes, and extended system/ERD/DFD diagrams in `docs/non-functional-requirements.md`.
- Development roadmap is now formalized both in `docs/development-roadmap.md` and the machine-readable `/api/v1/roadmap` endpoint so build order, gates, and remaining milestones stay explicit.
- Phase-by-phase verification reporting is now formalized in `docs/verification-reports.md` and the machine-readable `/api/v1/verification` endpoint, including sample input/output and baseline comparisons.
- WebSocket room manager for streaming chat and live workspace collaboration channels.
- Model adapter registry for Groq, OpenAI, Claude, Ollama, and Gemini boundaries.
- FAISS-style vector store abstraction, lightweight knowledge graph builder, session cache abstraction, and object storage abstraction.
- Responsive frontend shell, Docker Compose, SQL schema, and CI workflow.
- CI workflow now includes dependency review, `pip-audit`, enforced `npm audit`, and Trivy filesystem vulnerability scanning.

## Not yet complete

- Real FAISS integration
- Real OCR engine integration
- Real PDF binary parsing via PyMuPDF
- Real LLM provider adapters to Groq/OpenAI/Claude/Gemini/Ollama
- Supabase auth and RLS wiring
- Real-time CRDT collaboration, production-grade PWA sync, rich editor UX, and the rest of the product surface
- Real Supabase token rotation, managed key storage, push delivery infrastructure, and production-grade encrypted note persistence
- Production GraphQL resolver stack, real third-party OAuth/import adapters, signed browser-extension release packaging, and deeper agent-evaluation loops

## Honest status

The prompt describes a multi-phase product that would normally take a team and repeated implementation cycles. This repo is now a stronger working baseline, but it is not truthful to call all 400+ requested features complete yet.
