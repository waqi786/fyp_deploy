# Temporary team demo deployment

This copy is isolated from the development workspace. It excludes `.env`, local databases, storage, backups, models, and generated dependencies.

## Vercel frontend

- Import the GitHub repository `waqi786/fyp_deploy`.
- Set the project Root Directory to `apps/web`.
- Set `VITE_API_BASE_URL` to `https://resora-demo-api.onrender.com/api/v1`.
- Build command: `npm run build`; output directory: `dist`.
- `apps/web/vercel.json` supplies SPA route rewrites.

## Render API and demo database

- Create a Blueprint from the same GitHub repository; Render reads `render.yaml`.
- The blueprint provisions the FastAPI Docker service and a temporary free Postgres database.
- Set `CORS_ALLOWED_ORIGINS` to the actual Vercel deployment origin if it differs from the configured demo URL.
- Add provider keys only in Render's secret environment settings; never commit them.

Free Render API instances sleep when idle, and free Postgres is temporary. This setup is for a short supervisor/team demo, not production. Uploaded local files can disappear when the service restarts; do not upload private or irreplaceable documents.
