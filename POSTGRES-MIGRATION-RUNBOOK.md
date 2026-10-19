# BhuDrishti PostgreSQL/Supabase migration and deployment runbook

## 0. Protect data first

1. Create a Supabase backup or database snapshot.
2. Keep an untouched copy of `backend/data/bhudrishti.db` and `backend/data/uploads/`.
3. Do not run the SQLite importer against production until you know whether those records are already present in Supabase. The importer inserts missing rows only and reports conflict counts; it does not overwrite or delete destination rows.

## 1. Inspect the existing Supabase users schema

Run this read-only SQL in the Supabase SQL editor before migrating:

```sql
SELECT table_schema, table_name, column_name, data_type, is_nullable
FROM information_schema.columns
WHERE table_schema = current_schema()
  AND table_name IN ('users', 'datasets', 'extractions', 'verifications', 'schema_migrations')
ORDER BY table_name, ordinal_position;

SELECT COUNT(*) AS duplicate_case_insensitive_emails
FROM (
  SELECT lower(email) AS email_key
  FROM users
  WHERE email IS NOT NULL AND btrim(email) <> ''
  GROUP BY lower(email)
  HAVING COUNT(*) > 1
) d;
```

If `users` has duplicate case-insensitive emails, reconcile them manually before running migrations. The migration intentionally aborts instead of merging/deleting accounts. Existing rows with no usable email are preserved but cannot be used for email/password login until an administrator maps the account data correctly.

## 2. Configure a trusted local shell

Install the dependencies from the repository root:

```bash
python -m pip install -r requirements.txt
```

Set `DATABASE_URL` to the PostgreSQL/Supabase connection string. Use the connection URI supplied by Supabase; keep SSL enabled (`sslmode=require`) and URL-encode special characters in the password. Prefer a suitable pooled connection string for Vercel. Never commit the URI or paste it into logs.

Generate a strong auth secret locally:

```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

Set it as `BHUDRISHTI_AUTH_SECRET` in Vercel. It must be at least 32 characters. Do not use the prototype fallback secret.

## 3. Apply schema migration

From the repository root, with `DATABASE_URL` set in your local shell:

```bash
python backend/migrate_postgres_schema.py
```

Expected output is `POSTGRES_SCHEMA_MIGRATION: PASS`. The migration is additive and repeatable. It uses a PostgreSQL transaction-scoped advisory lock to serialize concurrent migration runners, adds missing columns without dropping existing rows, backfills `users.user_id` from `id` if that legacy column exists, otherwise derives a stable identifier from email, creates uniqueness indexes only after duplicate checks, and creates/synchronizes `extraction_id_seq`.

If it fails, stop and inspect the schema/error class. Do not drop or recreate tables. Resolve duplicate or incompatible legacy data deliberately, then rerun.

## 4. Import the bundled SQLite data only if required

After schema migration and after confirming the data is not already present in Supabase:

```bash
python backend/migrate_sqlite_to_postgres.py --sqlite backend/data/bhudrishti.db --uploads backend/data/uploads
```

This operation does not modify the SQLite source or upload files. It stores upload bytes in PostgreSQL `BYTEA`, imports extraction geometry as WKT, and preserves verification/audit JSON. Existing destination keys are skipped rather than overwritten; compare the reported inserted/skipped counts with expected records before cutover. Do not assume a skipped conflict is equivalent until the destination record has been checked.

## 5. Vercel configuration

In Vercel Project Settings:

- **Root Directory:** repository root (`.`), not `backend/`.
- **Framework Preset:** Other.
- **Build/Install:** default dependency install from root `requirements.txt`.
- **Output Directory:** blank.
- **Production environment variables:**
  - `DATABASE_URL` — managed PostgreSQL/Supabase URI.
  - `BHUDRISHTI_AUTH_SECRET` — generated random value, minimum 32 characters.
  - `BHUDRISHTI_DB_CONNECT_TIMEOUT` — optional integer, defaults to `8`.

The root `vercel.json` routes requests to `api/index.py`, which imports `backend.app.main:app`. Delete the nested `backend/vercel.json` from the Git repository (it is intentionally absent from the patch ZIP) and ensure the Vercel Root Directory is the repository root. `psycopg[binary]==3.2.9` is already present in both root and backend requirements files, so no dependency-manifest edit was needed.

Demo credentials are disabled in production even if corresponding legacy rows are imported. The login page no longer publishes their passwords. If no real active administrator exists, create the first one interactively (the password is not echoed or printed):

```bash
python backend/bootstrap_admin_user.py
```

This command requires `DATABASE_URL`, runs the same safe schema migration, refuses demo email addresses, refuses to overwrite an existing account, and refuses to create a second active non-demo administrator. Do not re-enable the built-in demo passwords on a public deployment.

## 6. Post-deployment verification

After deploying the commit:

1. `GET https://bhudrishti-api.vercel.app/api/health` should return HTTP 200 with `persistence.adapter = "postgresql"`, `configured = true`, `connected = true`, and `schema_ready = true`. If configuration is present but the DB is unreachable, expect HTTP 503 with a sanitized error type; if connected but migrations are missing, expect `schema_ready = false` and HTTP 503.
2. Authenticate with a non-demo production account and call `GET /api/system/status`; it must report backend online and production storage connected.
3. Call authenticated `GET /api/survey-queue` and verify expected queue records.
4. Upload an orthophoto and verify it can be retrieved from a separate invocation via `/api/datasets/{dataset_id}/file`.
5. Run extraction -> submit correction -> certify -> export. Verify status, WKT geometry, and audit history persist across separate requests and Vercel instances.
6. Inspect Vercel Runtime/Function Logs for the deployed commit and startup errors. Do not share connection strings, tokens, password hashes, or secrets.

No live Supabase connection, Vercel environment configuration, or production deployment was available during this repair. Local tests do not establish that the live deployment is fixed; declare it fixed only after these checks pass against the deployed API.
