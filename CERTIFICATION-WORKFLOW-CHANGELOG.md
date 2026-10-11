# Certification Workflow Repair — Changelog

## Root cause

`frontend/field-verification.html` treated `unverified` as an implicit preliminary-acceptance action and sent every other status to `/api/verification/{parcel_id}/certify`. The backend state machine intentionally permits certification only from `in_review`, so an already `verified` record received HTTP 409. The previous frontend also rendered failed status reads as `unverified`, which could misrepresent authoritative state, and did not consistently keep action availability aligned with the refreshed status.

## Source files changed

- `frontend/field-verification.html`
  - Explicitly handles `unverified`, `in_review`, `verified`, and `rejected`.
  - Re-reads `GET /api/verification/{parcel_id}` immediately before the action and after state changes.
  - `unverified`: only `ADMIN` and `REVENUE_OFFICER` may explicitly accept AI preliminary geometry, after a confirmation prompt. Other roles are directed to submit a correction for review.
  - `in_review`: invokes the certification endpoint and requires both its response and a subsequent authoritative GET to confirm `verified`.
  - `verified`: does not send a certification POST; refreshes backend state and offers navigation to Export.
  - `rejected`: blocks certification in the UI and explains that corrected geometry must be resubmitted.
  - API errors leave the state unavailable rather than silently displaying `unverified`; status-specific actions are disabled while authoritative state cannot be loaded.
  - Keeps the existing Stitch layout, typography, colors, and controls.
- `backend/app/verification_store.py`
  - Makes repeated certification of an already verified record idempotent: returns the existing record unchanged without changing geometry or appending a duplicate audit event.
  - Keeps the state-machine rule that only `in_review` can transition to `verified`; rejected/unreviewed records cannot bypass review through this endpoint.
  - Requires submitted review geometry for the `in_review` certification transition instead of substituting AI geometry.
- `backend/test_certification_workflow.py`
  - Adds isolated API/state-machine regression tests using temporary SQLite databases for verification, extraction, and auth. The included project database and user data are not modified by these tests.

## State behavior

| Backend status | Certification action |
|---|---|
| `unverified` | Authorized `ADMIN`/`REVENUE_OFFICER` may explicitly confirm acceptance of preliminary AI geometry; other roles must submit a correction for review. |
| `in_review` | Calls certification; successful response must be followed by an authoritative GET showing `verified`. |
| `verified` | No certification POST; refreshes state, avoids duplicate audit entries, and offers Export. |
| `rejected` | Certification is blocked until corrected geometry is submitted again and enters `in_review`. |

The certification route continues to update the extraction status to `verified`; because the store returns the unchanged verified record on retries, the route can repair a stale extraction status without duplicating the certification audit event. Export resolves the verified geometry through the existing `_target_geometry` path and includes the authoritative verification status.

## Automated results

Executed successfully:

- `python backend/test_sprint2_backend_correctness.py` — PASS
- `python backend/test_sprint3_geospatial_semantics.py` — PASS
- `PYTHONPATH=. python backend/test_sprint4_differentiation.py` — PASS
- `python backend/test_active_orthophoto_rendering.py` — PASS
- `python backend/test_certification_workflow.py` — PASS; covers review submission, certification, idempotent repeat, rejection/resubmission, role restrictions, unauthenticated access, and exported certified geometry/status.
- `python -m py_compile backend/app/verification_store.py backend/app/main.py backend/test_certification_workflow.py` — PASS
- Node syntax check for all four inline scripts in `frontend/field-verification.html` — PASS

The Sprint 4 script requires `PYTHONPATH=.` because its original import setup does not add the repository root itself; it passed with that environment. Browser-driven UI testing was not performed, so the visual/click workflow remains unverified in a real browser. No deployment claim is made.
