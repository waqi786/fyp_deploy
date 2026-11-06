# Resora FYP Advanced

Resora is an AI research assistant and knowledge copilot for academic paper discovery, understanding, comparison, grounded chat, research gap detection, and literature review drafting.

## Monorepo Layout

```text
apps/
  api/        FastAPI backend
  web/        React + Vite frontend
docs/         Architecture, checklist, verification and proposal-alignment docs
infra/        Database and deployment support
supabase/     Database migrations
scripts/      QA and demo automation scripts
Proposals/    Proposal documents live one level above this app folder
```

## Local Development

API:

```bash
cd apps/api
pip install -e .
python -m uvicorn app.main:app --reload --port 8000
```

Web:

```bash
cd apps/web
npm install
npm run dev
```

Open:

- Web app: `http://127.0.0.1:5173`
- API docs: `http://127.0.0.1:8000/docs`

## Paper comparison

Compare accepts 2–15 uploaded PDFs. It validates and extracts PDF text, stores the files and extracted text in the configured database, and builds the table only from those uploaded files. Cells with matching text include a PDF page reference; the Evidence panel can open the stored PDF. Search results now open Compare without adding metadata to the table.

PDF upload limits, storage, privacy requirements, and current processing limitations are documented in [the API guide](docs/api.md). The comparison data is scoped to the authenticated owner; production deployments must configure verified authentication.

## Verification

```bash
cd apps/api
python -m pytest app/tests -q

cd ../web
npm run typecheck
npm run build
```

## Demo Assets

Presentation video and posters are in `marketing images/`.
