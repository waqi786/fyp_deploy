# Master Feature Assurance

Resora exposes the complete implementation assurance matrix at:

- API: `GET /api/v1/verification/features`
- UI: `/assurance`

The matrix tracks the master prompt as implementation categories with:

- `feature_key`
- `feature_name`
- `enforcement_status`
- `acceptance_criteria_count`
- `automated_check`
- `verification_command`
- `route`
- `evidence`
- `capabilities`
- `production_notes`

## Status Language

- `DONE`: code-level workflow exists, is wired into the API/UI, and is covered by smoke tests.
- `BLOCKED`: launch-critical work cannot be honestly marked production-ready until live infrastructure validation happens.
- `PARTIAL`: reserved for future rows where some but not all criteria are implemented.

## Current Coverage

The current assurance matrix tracks `363` named capabilities:

- `357` are code-level smoke verified.
- `6` are intentionally blocked public-launch gates.

The blocked gates are not feature omissions. They are real deployment requirements:

- public domain + HTTPS
- live production credentials
- production database/RLS validation
- monitoring and alert delivery
- backup/restore drill
- `50+` concurrent-user staging load test

## Required Commands

Backend:

```powershell
cd apps/api
python -m pytest app\tests -q
```

Frontend:

```powershell
cd apps/web
npm run typecheck
npm run build
```

Production env:

```powershell
python scripts\validate_production_env.py --env-file .env.production.local
python scripts\launch_gate.py --env-file .env.production.local
```

## Honesty Rule

The app must not be represented as world-scale public production-ready until the launch gate passes against a real deployment environment.
