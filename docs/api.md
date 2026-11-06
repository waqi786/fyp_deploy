# Resora API

## Local endpoints

- Root service probe: `GET /`
- Health check: `GET /api/v1/health/`
- OpenAPI JSON: `GET /openapi.json`
- Swagger UI: `GET /docs`

## Versioning

All product endpoints are mounted under `/api/v1`.

## Local verification

1. Start the API with `python -m uvicorn app.main:app --reload --port 8000` from `apps/api`.
2. Open `http://127.0.0.1:8000/docs`.
3. Call `GET /api/v1/health/` and confirm `{"status":"healthy"}`.

## Notes

The OpenAPI document is generated directly from FastAPI route declarations. As feature modules expand, this document
should be paired with endpoint-level examples and authentication notes.

## PDF-only Compare

The Compare page accepts uploaded PDF files and does not use Search metadata, abstracts, DOI lookups, or publisher URLs
as table sources. The legacy `POST /api/v1/comparison/` resolver remains available for existing integrations; the
Compare UI uses only the PDF routes below.

| Method | Route | Purpose |
| --- | --- | --- |
| `GET` | `/api/v1/comparison/pdfs/limits` | Return maximum file count, file size, and page count. |
| `GET` | `/api/v1/comparison/pdfs?comparison_id={uuid}` | List the current user's files for one comparison. |
| `POST` | `/api/v1/comparison/pdfs/upload` | Upload one or more PDFs as multipart `files`; accepts `comparison_id`. |
| `POST` | `/api/v1/comparison/pdfs/run` | Compare 2–15 saved file IDs using PDF text only. |
| `GET` | `/api/v1/comparison/pdfs/{file_id}` | Stream an owner's PDF with private, no-store caching. |
| `DELETE` | `/api/v1/comparison/pdfs/{file_id}` | Delete the owner's PDF and extracted text from the database. |

The server enforces the PDF signature, configured byte and page limits, encryption checks, duplicate SHA-256 detection,
and ownership checks. Defaults are 15 PDFs per comparison, 50 MiB per file, and 120 pages per PDF; configure
`COMPARISON_MAX_PDF_BYTES` or `COMPARISON_MAX_PDF_PAGES` to change the latter limits. PostgreSQL stores the PDF bytes,
extracted text, owner, file name, hash, page count, and extraction method in `comparison_pdf_files`. SQLite development
uses the same logical table; the root Docker Compose file mounts its database volume for persistence.

The web client discloses that PDFs are stored and can be removed. Production deployments must configure
`SUPABASE_JWT_SECRET` and send a verified bearer token; unverified browser identity headers are rejected in production.
The current repository does not include malware scanning, resumable/chunked uploads, background or streaming extraction
jobs, credit reservation/refund, comparison history, or a separate asynchronous Insights job. Scanned PDF OCR depends on
Tesseract being installed in the API runtime; otherwise the upload is rejected with a readable error. Extracted table
facets remain heuristic and should be reviewed against the cited PDF page before publication.
