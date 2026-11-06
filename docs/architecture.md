# Resora Architecture

Resora is structured as a multi-service platform that preserves the validated ReSearch Flow foundations while
swapping paid dependencies for free-tier-first infrastructure where possible.

## Runtime services

- `api`: FastAPI application serving versioned REST endpoints under `/api/v1` and the OpenAPI document.
- `worker`: Background Python worker for cache-warming and long-running asynchronous tasks.
- `web`: React 19 + Vite frontend with a TypeScript router shell and PWA assets.
- `postgres`: Primary relational store for shared paper cache, user workspaces, and AI-output metadata.
- `redis`: Session persistence and short-lived caching.
- `minio`: Object storage for figures and derived artifacts in local and self-hosted deployments.
- `neo4j` (optional): Acceleration path for citation-graph workloads.

## Application layers

- Presentation layer: React frontend, responsive shell, theme and RTL toggles.
- API layer: FastAPI routers, schema validation, and orchestration endpoints.
- Reasoning layer: provider-agnostic model adapters and specialist agents.
- Retrieval layer: hybrid retrieval, chunking, vector store, and citation graph services.
- Persistence layer: Postgres, Redis, MinIO, and optional Neo4j.

## Current Phase 0 alignment

- Health-check API is live.
- Docker Compose scaffolding exists both at repo root and under `infra/`.
- CI workflow runs backend tests, frontend build, dependency audit, and filesystem vulnerability scanning.
- Frontend now has a TypeScript + React Router entry shell while preserving the existing dashboard.
