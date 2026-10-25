# BhuDrishti production authentication repair

## Root cause found

The PostgreSQL `users` table can contain a legacy workspace-based schema (`workspace_id NOT NULL` plus role/status CHECK constraints limited to lowercase values). BhuDrishti's auth code inserts `ADMIN`, `PROJECT_OFFICER`, etc. without a workspace ID. That schema mismatch causes bootstrap/registration inserts to fail even when the database connection itself works. The old health check also trusted migration-version rows without checking the actual auth schema.

## What this patch changes

- Auth schema migration v4 makes a legacy `workspace_id` column nullable and removes only CHECK constraints whose definitions reference `role` or `status`.
- Existing user rows, IDs, workspace rows, workspace values, and foreign keys are retained. No user/workspace tables are dropped.
- Bootstrap inserts according to BhuDrishti's auth schema rather than creating/looking up a workspace.
- Auth treats legacy lowercase `active`/`admin` values case-insensitively and returns normalized role/status values.
- `/api/health` checks the required auth columns and the workspace nullability condition as well as migration versions.

## Apply safely (PowerShell)

1. Take a Supabase backup/snapshot first. Keep `DATABASE_URL` private; do not paste it into chat or commit it.
2. Use the patched source and install dependencies from the repository root:

   ```powershell
   python -m pip install -r requirements.txt
   ```

3. Confirm your local PowerShell session has the intended Supabase URL set without printing it:

   ```powershell
   if (-not $env:DATABASE_URL) { throw 'DATABASE_URL is not set in this PowerShell session' }
   ```

4. Run the migration from the repository root:

   ```powershell
   python backend\migrate_postgres_schema.py
   ```

   Expected: `POSTGRES_SCHEMA_MIGRATION: PASS`. If it fails, stop and review the database schema before retrying; do not drop/recreate tables.

5. Create the real admin account (password prompts do not echo the password):

   ```powershell
   python backend\bootstrap_admin_user.py
   ```

   Use a strong password of at least 12 characters. The script refuses to overwrite an existing account and refuses a second active non-demo administrator.

6. Deploy the patched source to Vercel. Ensure the project root is the repository root and production environment variables include `DATABASE_URL` and `BHUDRISHTI_AUTH_SECRET` (random secret, at least 32 characters). Redeploy after changing environment variables.

7. Verify `https://bhudrishti-api.vercel.app/api/health`: it should return HTTP 200 with `adapter=postgresql`, `connected=true`, and `schema_ready=true`. Then test login at `https://bhudrishti.netlify.app` with the administrator account.

## Validation boundary

All bundled backend regression scripts and Python compilation passed locally. The PostgreSQL integration test was skipped because no live test database URL was supplied. This patch has **not** been verified against your live Supabase database or deployed to Vercel; declare production auth fixed only after the health and login checks above pass.
