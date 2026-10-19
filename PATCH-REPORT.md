# BhuDrishti PostgreSQL startup/schema repair

## Scope and evidence

Inspected the supplied ZIP, including `api/index.py`, both Vercel configs, `backend/app/{main,auth,database,persistence,verification_store,extraction_store,repositories}.py`, the geometry/confidence/elevation/extraction engines, the SQLite importer, requirements, frontend API client, and existing tests.

The supplied archive's `auth.py` does contain an `ALTER TABLE users ADD COLUMN IF NOT EXISTS user_id` attempt before the failing `SELECT user_id`. Therefore, the live traceback alone does not prove the exact live table layout or that Vercel is running the exact same artifact/configuration as this ZIP. The confirmed source-level defect is that schema DDL and legacy repair were embedded in import/request-time paths, distributed across modules, and not managed as a single explicit migration. `CREATE TABLE IF NOT EXISTS` cannot upgrade an existing table, and the module-level verification repository attempted DDL during import. These are the unsafe patterns repaired here. A live database schema inspection is still required to distinguish stale deployment/configuration from an additional schema variant in Supabase.

## Changes

- `backend/app/database.py`: central additive schema migration, legacy user identifier backfill (`id` -> `user_id` when that column exists; otherwise stable email-derived ID), duplicate checks before unique indexes, migration ledger v3, PostgreSQL transaction advisory lock, SQLite `BEGIN IMMEDIATE`, and truthful connection/schema readiness status. SQL values remain parameterized; no DSN or raw exception text is returned by health checks.
- `backend/app/auth.py`: removed runtime DDL from `_connect`; demo users are seeded only in local development, inserted idempotently, and existing passwords are never reset at startup/login. Production demo-email login and token fallback are disabled. Vercel requires `BHUDRISHTI_AUTH_SECRET` of at least 32 characters.
- `backend/app/extraction_store.py`, `backend/app/verification_store.py`: constructors no longer create/alter tables at module import. Geometry WKT, JSON metadata/audit, row locking, and transaction boundaries remain. Verification store connections use the configured local DB path consistently.
- `backend/app/main.py`: production imports do not run PostgreSQL DDL or connect before FastAPI can serve health; local SQLite still initializes for development. Health/status report degraded until both connectivity and required schema versions are verified. Dataset bytes remain in PostgreSQL `BYTEA`; the production path does not write uploaded files to Vercel's read-only filesystem.
- `backend/migrate_postgres_schema.py` (new): explicit, repeatable, advisory-locked schema migration command.
- `backend/migrate_sqlite_to_postgres.py`: invokes the central schema migration before import; inserts missing records only, preserves source SQLite/upload files, imports file bytes, handles legacy user IDs, and synchronizes the extraction sequence.
- `backend/bootstrap_admin_user.py` (new): securely creates a first real production administrator without echoing the password, and refuses overwrites or demo email addresses.
- `frontend/auth.html`: removed published demo passwords while retaining the existing login design and access messaging.
- `AUTH-RBAC-PROTOTYPE.md`: corrected the production persistence/security description and removed the published password list.
- Tests: updated production-import/health expectations, isolated survey-queue tests from the bundled DB, and added schema idempotency/concurrency/legacy-user/placeholder tests.
- `backend/vercel.json` deleted from the source tree. Use the repository-root `vercel.json` and root directory `.` only; the nested file would create an alternate deployment path if the project root were set incorrectly. Because the deliverable is a changed-files-only ZIP, the deletion is recorded in this report and must also be applied in the Git repository.

No frontend files were changed. The bundled SQLite database was restored byte-for-byte to the version in the supplied ZIP after local tests; its SHA-256 was verified as `4b0b9baf8d31034d042a49755f3521dffa2211f66b92105f11b62f8ffc34189f`.

## Important production caveat

PostgreSQL schema migrations are now explicit. Before deploying this source, run `python backend/migrate_postgres_schema.py` against the intended Supabase database. Then import SQLite data only if needed. Do not enable SQLite as a production fallback. A live PostgreSQL server was not available in this environment, so the DDL and serverless behavior have not been verified against your actual Supabase project.
