# BhuDrishti — Sprint 1: Trust Repair

This package is a trust-focused prototype hardening pass. The existing Stitch/GIS visual design is preserved.

## Implemented

1. **Auth page no longer probes protected status APIs before login**
   - `auth.html` stays public.
   - Shared system-status/topology calls are skipped on the auth page.

2. **Field Verification evidence was made truthful**
   - Removed fabricated surveyor identity/license/authority/session claims.
   - Removed fake GNSS/GCP observations, survey photographs, spectral-match score, and hard-coded topology result.
   - Backend-derived confidence, elevation and topology values are shown when available.
   - GNSS/GCP/field-photo evidence is explicitly marked as not connected.

3. **Client-side certification fallback was removed**
   - Verification reads now come from the backend.
   - Browser localStorage can no longer create a `verified` record after an API failure.
   - Legacy local verification records are ignored.
   - Local extraction continuity remains preliminary only.

4. **Topology Validation no longer simulates remediation**
   - Removed fake Delaunay/sliver merge, SHP export, summons, and Form-4 UI actions.
   - Live Shapely/GEOS issue rows remain the source for topology review.
   - Re-run audit remains backend-driven.

5. **Prototype/legal semantics were tightened**
   - Certification is labelled as a prototype application workflow.
   - Government registry/e-signature/GNSS integrations are explicitly disclosed as not connected.
   - Demo reference layers are labelled as demo/reference rather than authoritative field evidence.

6. **Demo authentication is more stable across Vercel instances**
   - Built-in demo user IDs are deterministic.
   - Signed tokens carry employee/department context.
   - Only built-in demo users can be reconstructed when a temporary serverless SQLite row is missing.
   - Registered users are still rejected if their persistent account row is unavailable.

7. **Deployment continuity**
   - Frontend uses same-origin `/api/...` calls in production, allowing the Netlify `/api/*` proxy to route to Vercel.
   - `frontend/netlify.toml` explicitly publishes the frontend root.

## Important remaining limitations

- SQLite on Vercel `/tmp` is not durable/shared production storage.
- GNSS, government registries, digital signatures, real field photos and statutory integrations are not implemented.
- This sprint does not implement real shadow/parallax correction, georeferencing, or a trained ML model.
- Those belong to later sprints.

## Verification checklist

### Browser
1. Open `auth.html` while logged out.
2. Confirm there is no red "Backend unavailable" status banner caused by protected API calls.
3. Login with a built-in demo account.
4. Open Field Verification for `BD-047`.
5. Confirm there is no Rajesh Varma/license/SoI/GNSS/GCP/62% Spectral Match/fake field-photo evidence.
6. Confirm confidence/elevation/topology values load from the backend.
7. Temporarily disconnect the backend and click Submit/Certify/Reject. The action must fail visibly; it must **not** create a local verified state.
8. Open Topology Validation. Confirm no fake remediation buttons or simulated success messages exist.
9. Re-run the topology audit and confirm rows come from the backend.

### Static/code checks
- `node --check frontend/js/api-client.js`
- `python -m py_compile backend/app/auth.py backend/app/main.py`
