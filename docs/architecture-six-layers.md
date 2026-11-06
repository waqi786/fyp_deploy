# Resora Six-Layer Architecture

## Presentation Layer

- React 19 + Vite app shell
- Tailwind-ready styling pipeline
- PWA manifest and service worker
- Theme switching: dark, light, high-contrast
- RTL Urdu toggle through document direction

## API and Orchestration Layer

- FastAPI versioned routes under `/api/v1`
- WebSocket rooms for chat and workspace collaboration
- CORS-enabled app entry

## AI Reasoning Layer

- Model-agnostic adapter registry
- Groq default adapter
- OpenAI, Claude, Ollama, and Gemini adapter boundaries
- Planner plus specialist multi-agent orchestration

## Retrieval and Knowledge Layer

- BM25 plus dense RRF hybrid retrieval
- FAISS-style local vector store abstraction
- Knowledge graph builder for papers, authors, and concepts
- Session cache abstraction for Redis-style TTL storage

## Data Source Layer

- OpenAlex
- arXiv
- CORE
- PMC
- Semantic Scholar
- Google Scholar
- Crossref
- Unpaywall

## Persistence and Infra Layer

- Postgres schema with shared research paper cache
- Object storage abstraction for extracted figures
- MinIO service in Docker Compose
- Redis and Neo4j optional services
- GitHub Actions CI plus benchmark smoke check
