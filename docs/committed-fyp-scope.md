# Committed FYP Scope QA

This document mirrors the supervisor-facing scope lock from the committed build prompt.

## Product Surface

- API: `GET /api/v1/verification/committed-scope`
- UI: `/assurance?focus=committed-scope#committed-scope`

## Enforced Defaults

- The default search path uses only the six committed free/open sources:
  - OpenAlex
  - arXiv
  - Semantic Scholar
  - Crossref
  - CORE
  - PubMed Central
- Google Scholar/SerpAPI are excluded from the committed default path.
- The defended AI path is Groq plus FAISS-lite/local retrieval; paid providers are not required for the FYP path.

## Honest Status Rules

Every committed item is labelled as:

- `✅ DONE`: implemented, regression-tested, and mapped to a product route.
- `⚠️ PARTIAL`: usable but still needs production hardening or real deployment validation.
- `❌ BLOCKED`: not usable without external credentials, infrastructure, or a missing dependency.

The current matrix intentionally marks OCR, binary figure/table extraction, production auth, and real provider hardening as partial where live infrastructure validation is still needed.

## Out Of Scope For The Defended FYP

- Real-time multi-user collaboration on literature reviews
- Plagiarism checking
- Zotero/Mendeley integration
- Journal/conference recommendation engine
- Research-trend prediction using historical data

These can stay as later SaaS roadmap items, but they should not be presented as committed FYP deliverables.
