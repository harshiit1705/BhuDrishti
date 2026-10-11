# BhuDrishti persistence / verification 404 repair

## Confirmed root cause

`GET /api/extraction/{id}` and verification's `_target_geometry()` read the backend `extractions` table. The frontend API client previously returned a browser-local cached `EXT-*` object before asking the API, so Field Verification could render an extraction that did not exist in the backend instance receiving `POST /api/verification/{id}/submit`. Both `extraction_store.py` and `verification_store.py` selected `/tmp/bhudrishti/bhudrishti.db` when `VERCEL` was set. `/tmp` is per-instance ephemeral storage; a record created by one serverless instance is not guaranteed to exist in another. Dataset metadata and upload bytes were also stored in that ephemeral directory. The auth store used the same nominal path, but shared path text does not make the filesystem shared across instances.

The bundled `backend/data/bhudrishti.db` is local archive data and does not prove the deployed API contains `EXT-0001`. No live production endpoint was queried as part of this repair, so deployed `GET /api/extraction/EXT-0001`, `GET /api/extraction`, and submit behavior remain unverified.

## Exact source changes

- `backend/app/persistence.py` (new): centralizes DB and upload path configuration and prevents silent Vercel `/tmp` fallback.
- `backend/app/main.py`: dataset metadata, upload files, and API routes use the shared central `DB_PATH` / `UPLOAD_DIR`.
- `backend/app/extraction_store.py`: extraction repository uses the same central database path.
- `backend/app/verification_store.py`: verification records and audit history use the same central database path.
- `backend/app/auth.py`: user/authentication records use the same central database path.
- `backend/app/repositories.py`: persistence status identifies the configured SQLite file.
- `frontend/js/api-client.js`: `getExtraction(id)` always calls the API. Local workflow cache is no longer treated as authoritative.
- `frontend/field-verification.html`: extraction page load no longer falls back to cached extraction on backend failure; Save Draft, Certify, and Reject are disabled until authoritative target resolution succeeds. The original image is resolved from the extraction dataset ID and dataset-keyed cache, never from a potentially colliding EXT-keyed image cache; failed image retrieval no longer reveals seeded background imagery. Certification status handling explicitly blocks unverified/rejected states and makes verified records an export path.
- `backend/test_persistence_shared_instances.py` (new): isolated shared-file process test for extraction visibility, submit, certify, export geometry/status, missing-ID 404, and Vercel fail-fast.

No UI redesign was made. Existing layout and visual styling are retained.

## Persistence/deployment status

This source tree has SQLite implementations, but no PostgreSQL/Supabase repository adapter. Therefore this repair deliberately does **not** claim to have converted records to PostgreSQL or to have fixed Vercel persistence by merely setting a URL.

- Local development: SQLite remains at `backend/data/bhudrishti.db` by default.
- Isolated tests / explicit shared mounted storage: set `BHUDRISHTI_DB_PATH=/absolute/path/to/bhudrishti.db` for every process. This only provides cross-process sharing when the path is on the same genuinely shared/persistent filesystem; it is **not a solution for ordinary Vercel serverless instances**.
- Vercel: startup now fails closed unless the operator explicitly sets `BHUDRISHTI_ALLOW_EPHEMERAL_SQLITE=1` for temporary prototype-only use. That opt-in is unsafe and not a production fix. If `DATABASE_URL` or `BHUDRISHTI_DATABASE_URL` is present on Vercel, startup also fails because this build does not support PostgreSQL and must not silently ignore the URL.
- Durable production requirement: provision a managed PostgreSQL/Supabase database, add and test a PostgreSQL-capable repository adapter for users, datasets, extractions, verifications, and audit history, then set `DATABASE_URL` (or `BHUDRISHTI_DATABASE_URL`) to its private connection URI. Store upload bytes in durable object storage (for example Supabase Storage) or a supported persistent volume; do not use `/tmp`. Use a least-privilege DB role and TLS/SSL. This ZIP intentionally does not invent credentials or pretend this adapter/storage migration exists.

### Migration cautions

Do not replace the live database with the bundled fixture. Before production cutover, export existing users, datasets, extraction records, verification records including `audit_json`, and associated uploaded bytes from the actual live store if available; migrate in a transaction preserving primary IDs and status; verify row counts and geometry hashes; copy source image bytes to durable object storage; then switch API and frontend to the same production API. Per-instance `/tmp` data cannot be reliably recovered from the ZIP and may already have diverged or disappeared.

## Frontend API origin / routing

All pages use the shared `frontend/js/api-client.js`. Production default is same-origin API paths (`API_BASE_URL = ""`), and `frontend/netlify.toml` proxies `/api/*` to `https://bhudrishti-api.vercel.app/api/:splat`; the backend's `backend/vercel.json` routes requests to `app/main.py`. Localhost uses `http://localhost:8000`. This is a code/config trace only; the current Netlify and Vercel deployments were not queried live.

## Test execution

`backend/test_persistence_shared_instances.py` runs all persistence writes in a temporary directory. It starts one Python process to create `EXT-0001`, then a second process to read the same DB, submit review geometry, certify, and verify the exported geometry/status. It also asserts missing extraction returns 404 and Vercel fails fast without an unsafe opt-in.

The existing Sprint 2, Sprint 3, Sprint 4, and active-orthophoto test scripts are run separately in the repair validation. Browser testing and live deployment testing are not claimed.

## Executed regression results (this repair build)

Executed with `BHUDRISHTI_DB_PATH` pointed at a fresh temporary test DB (not the bundled database):

- `backend/test_sprint2_backend_correctness.py` — PASS
- `backend/test_sprint3_geospatial_semantics.py` — PASS
- `backend/test_sprint4_differentiation.py` — PASS
- `backend/test_active_orthophoto_rendering.py` — PASS
- `backend/test_certification_workflow.py` — PASS (submit/certify/repeat idempotency/rejected resubmission/roles/export)
- `backend/test_persistence_shared_instances.py` — PASS (two processes, GET single/list against same local app store, missing ID 404, submit/certify/export, Vercel fail-fast, routing/API-client contract)
- `python -m compileall -q backend/app` — PASS
- Inline JavaScript syntax checks — PASS (30 inline scripts)

Not executed: browser automation/screenshots; live Netlify/Vercel GET or POST requests; production database migration; managed PostgreSQL operation. Local multi-process tests prove only that processes configured with the same local SQLite file share records; they do not prove a Vercel deployment is fixed.
