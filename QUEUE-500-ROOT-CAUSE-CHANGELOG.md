# Survey Queue HTTP 500 — Forensic Findings and Repair

## Important production-verification limitation

Production Vercel Function Logs and the live Netlify/Vercel endpoints were not accessible from this execution environment (outbound DNS/network access failed). Therefore the exact production traceback, live API origin response, and deployed commit cannot honestly be reported as verified. The source-level failure below is reproduced locally, but it is a plausible production cause—not proof that this is the exact exception in the currently deployed function.

## Source-level root cause reproduced

`backend/app/extraction_store.py` used `CREATE TABLE IF NOT EXISTS extractions (...)` and then `_row()` unconditionally accessed `row["dataset_id"]`. `CREATE TABLE IF NOT EXISTS` does not alter a pre-existing table. A SQLite database created by a prior schema version without `dataset_id` therefore causes extraction hydration to raise `IndexError: No item with that key` (SQLite Row missing-column lookup) when `extraction_store.all()` runs. `/api/survey-queue` enumerates this repository before ranking any records, so this legacy schema condition produces HTTP 500. A stale `/tmp` database is one possible deployment path to that condition; live logs are required to confirm it is the production failure.

## Files changed

- `backend/app/extraction_store.py` — added a data-preserving, additive SQLite schema migration that adds missing `dataset_id` and records schema version 2 in `schema_migrations`; no database reset or row deletion.
- `backend/app/verification_store.py` — adds/records a schema migration version for the verification store, sharing the same migration ledger and database path. Existing verification rows and audit JSON are preserved.
- `backend/app/main.py` — extracts queue assembly into `_build_survey_queue()`, reads extraction records once per queue request for a consistent snapshot, logs full server-side exception traceback with diagnostic ID, and returns a sanitized HTTP 500 containing only a diagnostic ID. Repository failures are not converted to HTTP 200 or an empty queue.
- `backend/test_survey_queue_regressions.py` — isolated tests for legacy schema migration, record preservation, empty/seeded-only queue, valid and verified EXT records, missing IDs, and diagnostic failure behavior.

## Persistence warning

The existing persistence configuration remains honest: this code still uses SQLite prototype storage. It does not implement PostgreSQL and does not make Vercel `/tmp` durable or shared. Do not set `BHUDRISHTI_ALLOW_EPHEMERAL_SQLITE=1` as a production fix. A managed PostgreSQL adapter and durable object storage are still required for reliable multi-instance production data.

## Tests executed

Commands run from the project root:

```bash
PYTHONPATH=. python backend/test_sprint2_backend_correctness.py
PYTHONPATH=. python backend/test_sprint3_geospatial_semantics.py
PYTHONPATH=. python backend/test_sprint4_differentiation.py
PYTHONPATH=. python backend/test_certification_workflow.py
PYTHONPATH=. python backend/test_active_orthophoto_rendering.py
PYTHONPATH=. python backend/test_persistence_shared_instances.py
PYTHONPATH=. python backend/test_survey_queue_regressions.py
```

All seven scripts passed locally. The queue regression uses temporary isolated storage and does not modify the bundled database. Python/JavaScript syntax checks and ZIP integrity checks are reported separately in the delivery summary.

## Required production verification

1. In Vercel, open **Project → Deployments** and confirm the deployment commit SHA matches the intended GitHub commit and the deployment is Ready.
2. Open **Project → Functions → Logs** (or the deployment's Runtime Logs). Filter for `/api/survey-queue` around the user's request timestamp. Capture the exception type, traceback, file and line. Redact Authorization headers, tokens, cookies, connection strings, and environment values.
3. Check environment variable *names* and runtime configuration without sharing their secret values. If `BHUDRISHTI_ALLOW_EPHEMERAL_SQLITE=1` is set, the app can answer requests using per-instance `/tmp`; this is not durable.
4. Check `https://bhudrishti-api.vercel.app/api/health` and `/api/system/status`, then use an authenticated request to `GET /api/survey-queue` against that exact API origin. A 401/403 is an auth issue, a deployment/startup failure differs from an endpoint 500, and `/api/system/status` should still report SQLite prototype storage—not PostgreSQL.
5. Verify `frontend/_redirects` on the deployed Netlify publish output proxies `/api/*` to `https://bhudrishti-api.vercel.app/api/:splat`. Test `https://bhudrishti.netlify.app/api/health` and compare it with the direct Vercel health response.
6. Deploy this ZIP's source changes, then retest the queue. If the traceback points elsewhere, use that traceback as authoritative rather than assuming the legacy-schema hypothesis.
