# Operating Resora — admin console, growth, voices, SEO and launch checklist

## Admin console (`/admin`)

* Admins are the account ids in `ADMIN_USER_IDS` (comma-separated). In production the sign-in must be a verified
  (signed) JWT; the development header `X-Resora-User` is accepted only when `DEPLOYMENT_STAGE` is not `production`.
* Tabs: **Overview** (MRR per currency, 30-day revenue, trials, churn risk = cancelling or past-due subscriptions,
  new accounts and activation, active users 7/30 days, credits per feature, cookieless traffic, referrals, newsletter),
  **Users** (search, plan, usage, invoices, grant credits, suspend / restore), **AI providers** (health, quota,
  cool-down, probe now, routing per task, natural-voice engine), **Feature flags** (on/off + sticky percentage rollout +
  allow-list), **Jobs** (data-pipeline runs; failed payment webhooks kept as dead letters with safe retry),
  **Messages** (contact form), **Status** (incidents shown on `/status`), **Audit log** (every admin change).
* A suspended account gets `403 account_suspended` on every API route except health, the public status page and
  the admin API. Suspension is cached for 20 seconds per process.
* Flags the client can read: `GET /api/v1/site/flags`. Built-in flags: `listen.neural_voices`, `growth.referrals`,
  `growth.newsletter`, `search.catalog_source`, `insights.public_trends`.

## Growth and the public website

* Pages: `/welcome` (landing), `/features`, `/pricing`, `/about`, `/help` (searchable FAQ), `/contact`, `/status`,
  `/changelog`, `/legal/{privacy,terms,cookies,acceptable-use,refunds,dpa}`, `/invite`, `/newsletter/confirm`,
  `/newsletter/unsubscribe`.
* **Legal documents are templates for legal review** (`apps/web/src/pages/site/legalDocs.ts`): replace the
  `[bracketed]` placeholders and have a lawyer review them before launch.
* **Analytics are cookieless**: page path (ids and tokens stripped), referrer domain, language and device class;
  visitors are counted with a daily-rotating salted hash; no IP address is stored; Do Not Track and Global Privacy
  Control are respected.
* **Newsletter** is double opt-in. Set `SMTP_HOST`, `SMTP_PORT`, `SMTP_USERNAME`, `SMTP_PASSWORD`, `SMTP_FROM`,
  `SMTP_STARTTLS` and `PUBLIC_SITE_URL` to send confirmation e-mails. Without SMTP the address stays "pending".
* **Referrals**: each account has an 8-character code; the new account and the referrer both get `REFERRAL_CREDITS`
  (default 50) never-expiring credits, one redemption per account, referrer rewards capped at `REFERRAL_MAX_REWARDS`.
* **SEO**: `index.html` has default meta, Open Graph and JSON-LD; public pages set title, description, canonical and
  hreflang (`en`, `ur`, `x-default`) at runtime; `public/robots.txt` and `public/sitemap.xml` use
  `https://resora.example` — replace it with your domain and set `VITE_PUBLIC_SITE_URL`. For search engines that do
  not run JavaScript, prerender the public routes at build time (e.g. a static prerender step in your hosting).

## Natural voices

See `docs/TTS.md`. Start the voice server with `docker compose -f infra/docker-compose.tts.yml up -d` and set
`TTS_KOKORO_URL=http://localhost:8880` for the API. Pin `KOKORO_IMAGE` to a release tag in production.

## Continuous integration

`.github/workflows/ci.yml` runs: API lint, audit and tests (`tests/` + `app/tests/`), the data-pipeline tests (with
Java for Spark), the web i18n check, type check, build and audit, and the Playwright end-to-end suite.

## Launch checklist

1. `.env` (never committed) has real values for the database, auth secret, AI provider keys, billing provider and
   webhook secret, `ADMIN_USER_IDS`, SMTP, `PUBLIC_SITE_URL`, `VITE_PUBLIC_SITE_URL`, `CORS_ALLOWED_ORIGINS`.
2. PostgreSQL in production (`DATABASE_URL`, `CATALOG_DATABASE_URL`); the credit ledger (`CREDITS_DB_PATH`, SQLite)
   is per server — move it to PostgreSQL before running more than one API instance.
3. Billing: switch `BILLING_PROVIDER` from `sandbox` to your provider, set `BILLING_PROVIDER_PRICES`, register the
   webhook URL `/api/v1/billing/webhooks/{provider}` and test a real checkout, renewal, cancellation and refund.
4. Legal templates reviewed; company name, address and contact e-mails filled in.
5. Domain + TLS; robots/sitemap domain replaced; status page reachable.
6. Backups for PostgreSQL and object storage, with a tested restore.
7. Error monitoring and uptime checks; load test the target environment.
