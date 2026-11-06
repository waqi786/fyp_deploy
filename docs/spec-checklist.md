# Resora Master Checklist

This file translates the merged prompt into execution buckets so nothing is silently forgotten.

## Baseline preservation

- Preserve per-source service pattern for OpenAlex, arXiv, CORE, PMC, Semantic Scholar, Google Scholar.
- Keep exact DOI-first and normalized-title fallback deduplication logic.
- Keep chunking defaults `1200/200` and hybrid BM25 plus dense retrieval with `0.4/0.6` weighting.
- Keep deterministic chunk IDs and indexing verification loop.
- Keep citation-graph metrics: influence, PageRank, velocity, bridge detection.
- Keep shared paper cache design separate from user-owned data.

## Replacement work

- Swap Pinecone for FAISS or local dense index adapter.
- Swap OpenAI embeddings for Sentence Transformers.
- Swap paid GPT defaults for Groq or locally hosted providers behind an adapter.
- Add OCR fallback after PyMuPDF extraction failure.
- Add CI, mobile-first UI, and confidence scoring everywhere.

## Feature groups

- Search and discovery
- Paper understanding and summarization
- Trust and critique
- Multimodal extraction
- Comparison engine
- Gap and trend detection
- RAG chat
- Literature review generation
- Citation management
- Collaboration
- Accessibility and personalization
- Visualization
- Security and compliance
- Mobile and offline
- Extensibility and plugins
- Advanced multi-agent reasoning

## Engineering rule

Every new AI-generated entity should store:

- `confidence_score`
- `source_span`
- `model_used`
- `generated_at`
