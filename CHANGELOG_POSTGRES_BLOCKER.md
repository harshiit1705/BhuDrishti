# Changelog — managed PostgreSQL deployment blocker

## Implemented in source

- Added `backend/app/database.py`, a shared adapter using SQLite for local development and `psycopg` 3 for PostgreSQL. PostgreSQL uses dict rows, question-mark parameter translation, short connection timeout, and disabled client-side prepared statements for pooler compatibility.
- Replaced the Vercel ephemeral-SQLite opt-in guard with a fail-fast requirement for `DATABASE_URL` / `BHUDRISHTI_DATABASE_URL`. Added a production requirement for `BHUDRISHTI_AUTH_SECRET`.
- Routed authentication users, extraction records, verification records/audit trail, dataset metadata, and uploaded dataset bytes through the shared adapter. Orthophoto bytes are persisted as PostgreSQL `BYTEA`; old local upload files remain readable for local SQLite.
- Added versioned schema migrations for auth users, datasets, extractions, and verifications. Auth migration v4 repairs the legacy workspace-based PostgreSQL `users` schema by making `workspace_id` nullable and removing incompatible role/status CHECK constraints; existing rows, workspace values, and foreign keys are preserved. Legacy extraction `dataset_id` and dataset `content` columns are added without dropping records.
- Authentication now treats legacy lowercase `active`/`admin` values case-insensitively and returns normalized BhuDrishti role/status values. Health readiness checks the actual required user columns and legacy workspace nullability, not only migration version rows.
- Changed extraction upserts to portable `ON CONFLICT` SQL, added PostgreSQL-safe ID sequencing/sorting, and made verification transitions transactional with PostgreSQL row locks. Verification audit history and WKT geometry remain serialized persistently.
- Updated `/api/health` and `/api/system/status` to execute a real `SELECT 1` and report configured adapter, actual connection status, and degraded health truthfully.
- Added `backend/migrate_sqlite_to_postgres.py` for non-destructive SQLite import, including uploaded file bytes. Existing SQLite data and upload files are never modified by the importer.
- Updated both root and backend requirements to include `psycopg[binary]==3.2.9`; removed the conflicting nested `backend/vercel.json` so root `vercel.json` + `api/index.py` is the single documented Vercel entrypoint.
- Extended independent-process persistence checks to cover dataset bytes, health/status, extraction → submit → certify → export; added opt-in real PostgreSQL integration test.

## Tests run locally

- Sprint 2 backend correctness: PASS
- Sprint 3 geospatial semantics: PASS
- Sprint 4 differentiation: PASS
- Certification workflow: PASS
- Active orthophoto rendering contract: PASS
- Shared-instance persistence / API GET-404 / submit-certify-export / file bytes / health: PASS
- Survey-queue regressions, legacy schema migration and diagnostic 500 behavior: PASS
- Python compileall: PASS
- PostgreSQL integration: SKIPPED because no test database URL was configured. Package installation / live PostgreSQL verification could not be performed in this environment because outbound DNS/network access was unavailable.

## Important limitation

The code path and deployment configuration have been updated, but the production incident is **not declared fixed**. No live Supabase/PostgreSQL connection was available, no Vercel environment variables were configured from this environment, and no production deployment was made or verified. Follow `POSTGRES_DEPLOYMENT_AND_MIGRATION.md`, configure the database, import existing data, deploy, and verify `/api/health`, `/api/system/status`, queue behavior, and the full workflow on the actual Vercel deployment before considering it fixed.
