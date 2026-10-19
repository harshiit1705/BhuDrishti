# BhuDrishti managed PostgreSQL deployment

## What this build changes

- Vercel now fails fast unless `DATABASE_URL` (or the alias `BHUDRISHTI_DATABASE_URL`) is configured for PostgreSQL. There is no ephemeral SQLite fallback.
- `backend/app/database.py` is the shared DB-API adapter: SQLite is for local development; `psycopg` 3 connects to managed PostgreSQL/Supabase. Startup store initialization performs real database operations, so an unreachable database prevents the API from starting.
- Authoritative stores moved behind the shared adapter: registered/demo users and RBAC status, extraction records, verification state and audit trail, datasets and uploaded orthophoto bytes. Dataset bytes are in PostgreSQL `BYTEA`, not instance-local `/tmp` or local disk.
- Extraction geometry is stored as WKT; pixel polygons/candidates/roof footprints and verification audit entries are JSON. Verification state transitions use a transaction and PostgreSQL row locks; the extraction status update is committed in the same transaction.
- Additive version records are stored in `schema_migrations`; existing extraction schemas get the missing `dataset_id` column and existing dataset schemas get the `content` column without table resets.
- `/api/health` runs `SELECT 1`, reports adapter/configuration/connection truthfully, and returns HTTP 503 when the database cannot be reached. `/api/system/status` reports the same connection state and does not call PostgreSQL connected merely because a URL exists.
- The root-level `vercel.json` and `api/index.py` are the deployment entrypoint. Configure Vercel Root Directory as the repository root (`.`), not `backend/`.

Static `PARCELS` and the elevation/risk configuration remain deterministic demo/reference data; they are not user-created authoritative records. The old generic `InMemoryRepository` is retained only for compatibility and is not wired to API persistence.

## 1. Create a managed PostgreSQL database

1. Create a Supabase project (or another managed PostgreSQL database).
2. In Supabase, open **Project Settings → Database → Connect** and select the connection string appropriate for serverless use. Supabase's transaction pooler is suitable for Vercel; use the exact username/host/port shown by Supabase.
3. Use SSL (`sslmode=require`). URL-encode special characters in the database password. Do not commit the connection string or paste it into issue reports.

## 2. Configure Vercel

In **Vercel → Project → Settings → Environment Variables**, add these for **Production** (and Preview only if Preview deployments should connect to a separate test database):

| Name | Value |
|---|---|
| `DATABASE_URL` | Full PostgreSQL/Supabase connection URL, with SSL enabled |
| `BHUDRISHTI_AUTH_SECRET` | Strong random secret; generate locally with `python -c "import secrets; print(secrets.token_urlsafe(48))"` |
| `BHUDRISHTI_DB_CONNECT_TIMEOUT` | Optional; `8` seconds by default |

`BHUDRISHTI_DATABASE_URL` is supported as an alias, but prefer `DATABASE_URL`. Never set `BHUDRISHTI_ALLOW_EPHEMERAL_SQLITE`; this build intentionally does not support that fallback.

Project settings:

- **Root Directory:** repository root (`.`), where root `vercel.json`, root `requirements.txt`, and `api/index.py` exist.
- **Framework Preset:** Other.
- **Build Command / Install Command:** leave defaults unless your project has a deliberate custom command; Vercel should install the root `requirements.txt`, which includes `psycopg[binary]`.
- **Output Directory:** leave blank for the Python API project.
- Keep the frontend on Netlify as-is if its `_redirects` target still points to the correct Vercel API deployment (`https://bhudrishti-api.vercel.app/api/:splat`). If the API project URL differs, update that proxy target.

Redeploy after changing environment variables. Do not treat a successful build alone as proof of database connectivity.

## 3. Preserve and import the existing SQLite data

**Do not delete or overwrite `backend/data/bhudrishti.db` or `backend/data/uploads/`.** Back them up before migration. The import script leaves the source untouched.

Run from the repository root in an environment with network access to the managed database and dependencies installed:

```bash
python -m pip install -r requirements.txt
# Set DATABASE_URL in the shell only; do not add the secret to source control.
python backend/migrate_sqlite_to_postgres.py --sqlite backend/data/bhudrishti.db --uploads backend/data/uploads
```

PowerShell equivalent for setting a temporary shell variable:

```powershell
$env:DATABASE_URL = "<your PostgreSQL connection URL>"
python -m pip install -r requirements.txt
python backend/migrate_sqlite_to_postgres.py --sqlite backend/data/bhudrishti.db --uploads backend/data/uploads
```

The importer copies users/password hashes, datasets and file bytes, extractions/geometries, verification records, and serialized audit history. It inserts missing keys only (`ON CONFLICT DO NOTHING`), so it does not overwrite existing destination rows. It reports inserted and skipped counts. Review skipped counts before cutover; if the destination already has conflicting IDs, compare those records deliberately rather than resetting either database. The importer uses one destination transaction and does not modify the SQLite file or upload directory.

The app also runs idempotent additive schema setup on startup. The migration/import command is still needed to copy existing records; schema creation alone does not move data.

## 4. Deployment verification (required before calling production fixed)

After deploy, run these against the actual Vercel domain:

1. `GET /api/health` — expect HTTP 200 and `persistence.connected: true`, `persistence.adapter: "postgresql"`.
2. Authenticated `GET /api/system/status` — expect `persistence.connected: true` and `architecture.production_storage: "connected"`.
3. Authenticated `GET /api/survey-queue` — expect HTTP 200 with `queue`, `count`, and `contains_ai_extractions` fields.
4. Upload an orthophoto through Survey Projects; confirm the returned dataset file renders when navigating Survey Projects → AI Extraction → GIS → Topology → Elevation and back.
5. Run extraction, submit a correction as a field surveyor, certify it with an allowed role, then export GeoJSON. Confirm verified geometry and audit history survive a second request and a separate function instance.
6. Inspect Vercel Runtime/Function Logs for startup errors and `/api/survey-queue` errors. Never share the full connection URL or secrets in logs/screenshots.

If health returns 503 or startup fails, inspect the exception class in Vercel logs and verify the environment-variable scope, hostname, port, username, password encoding, SSL mode, database availability, and that the root directory is correct. A URL being present is not proof of connectivity.

## Local tests

Run the local regression suite with a disposable SQLite file (the bundled database is not needed for tests):

```bash
BHUDRISHTI_DB_PATH=/tmp/bhudrishti-test.sqlite3 PYTHONPATH=. python backend/test_sprint2_backend_correctness.py
BHUDRISHTI_DB_PATH=/tmp/bhudrishti-test.sqlite3 PYTHONPATH=. python backend/test_sprint3_geospatial_semantics.py
BHUDRISHTI_DB_PATH=/tmp/bhudrishti-test.sqlite3 PYTHONPATH=. python backend/test_sprint4_differentiation.py
BHUDRISHTI_DB_PATH=/tmp/bhudrishti-test.sqlite3 PYTHONPATH=. python backend/test_certification_workflow.py
BHUDRISHTI_DB_PATH=/tmp/bhudrishti-test.sqlite3 PYTHONPATH=. python backend/test_active_orthophoto_rendering.py
PYTHONPATH=. python backend/test_persistence_shared_instances.py
BHUDRISHTI_DB_PATH=/tmp/bhudrishti-test.sqlite3 PYTHONPATH=. python backend/test_survey_queue_regressions.py
```

For a real PostgreSQL cross-process integration test, use a disposable test database and set `BHUDRISHTI_TEST_DATABASE_URL` before running `python backend/test_postgres_integration.py`. That integration test is intentionally skipped if no test DSN is provided.
