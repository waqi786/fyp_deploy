# Resora Development Roadmap

This roadmap follows the requested build order and treats the existing ReSearch Flow-derived baseline as the starting point.

## Phase 1. Migrate Cost-Bearing Dependencies

- Swap Pinecone to FAISS-style local retrieval
- Swap OpenAI embeddings to Sentence-Transformers
- Swap GPT-4o/GPT-4o-mini defaults to Groq behind the adapter layer
- Swap GPT-4o Vision to free vision or OCR fallback
- Replace hard SerpAPI dependency with graceful-degrading Google Scholar fallback

Gate:
- Hybrid RAG should still meet or beat `~74%` accuracy before later phases proceed.

## Phase 2. Add OCR Fallback

- Add Tesseract-style scanned-PDF fallback to the document extraction path
- Reuse the same fallback in summarization and draft generation

Gate:
- Scanned PDFs should no longer fail silently in reading or writing flows.

## Phase 3. Extend Multimodal Retrieval

- Bring figures/tables into RAG retrieval scope
- Add equation extraction and equation-aware explanation

Gate:
- The historic figure/table failure mode should be explicitly targeted in evaluation.

## Phase 4. Raise Comparison Cap

- Increase comparison support from `5` to `10+`
- Add heatmaps, leaderboards, and custom columns

## Phase 5. Build Trust/Critique Agent

- Add Trust Score, Novelty Score, red flags, contradiction detection
- Add confidence scoring on every grounded answer

## Phase 6. Add Urdu Layer

- Extend Urdu support across summaries, chat, and UI
- Preserve RTL behavior and accessibility support

## Phase 7. Build Gap/Trend Agent

- Add white-space maps, publication trends, future-work suggestions, and gap questions

## Phase 8. Extend Drafting into Literature Reviews

- Build full literature-review generator
- Add self-critique, citation-style switching, and multi-format export

## Phase 9. Build Citation and Reference Management

- Add BibTeX/EndNote/RIS flows
- Add personal library and duplicate handling

## Phase 10. Build Collaboration and Workspace Layer

- Extend shared workspaces, RBAC, tasks, comments, and guest links

## Phase 11. Build Visualization and Analytics

- Extend citation mesh into analytics dashboards and graph views

## Phase 12. Build PWA, Mobile, Offline, Accessibility

- Installable PWA
- Offline reading and low-data mode
- Accessibility pass to WCAG 2.1 AA minimum

## Phase 13. Implement CI/CD and Ops Guardrails

- GitHub Actions
- Automated testing
- Vulnerability scanning
- Backup and monitoring posture

## Phase 14. Final Integration and Deployment Validation

- Run end-to-end integration checks
- Run `50+` concurrent-user validation
- Finalize documentation and deployment runbook

## Current Status

- Most feature slices are now present in code.
- The highest-risk open work remains true production validation of dependency swaps and final integrated load/deployment checks.
- The machine-readable roadmap is available through `/api/v1/roadmap`.
- Phase verification summaries are available through `/api/v1/verification`.
