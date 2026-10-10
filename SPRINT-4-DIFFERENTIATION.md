# BhuDrishti — Sprint 4: Differentiation

## Objective

Turn the existing elevation page's *claimed* shadow/parallax concept into an executable, inspectable prototype calculation without pretending that the current system has a measured DSM/DTM, solar ephemeris, CRS transformation, or legal cadastral correction engine.

## Implemented

### 1. Shadow/elevation evidence engine

Added `backend/app/shadow_engine.py`.

The engine performs:

1. `nDSM = DSM - DTM`.
2. Elevated-structure mask extraction from nDSM.
3. First-order cast-shadow projection from a supplied sun azimuth/elevation.
4. Predicted shadow length calculation using `height / tan(sun_elevation)`.
5. Dark-pixel comparison against luminance evidence.
6. Shadow IoU and shadow-contrast scoring.
7. A combined `shadow_consistency_score`.
8. A conservative overhang proxy.
9. A preliminary inward boundary candidate with explicit `legal_boundary: false`.
10. An evidence confidence score.

### 2. Uploaded-image bridge

For an `EXT-*` extraction with a persisted dataset, Sprint 4 can use the **actual uploaded image pixels as luminance evidence** while generating a clearly synthetic height surface from the extracted CV polygon.

This is intentionally described as:

`uploaded_orthophoto_plus_synthetic_elevation`

It is **not** described as a measured DSM.

If source-image dimensions do not support a valid pairing, the engine falls back to a deterministic synthetic paired scene.

### 3. API

New endpoint:

`GET /api/shadow/{parcel_id}`

Optional query parameters:

- `sun_azimuth_deg` — 0–360 degrees
- `sun_elevation_deg` — 1–89.9 degrees

The response exposes:

- predicted shadow direction and length
- elevated pixel count
- predicted shadow pixel count
- observed dark pixel count
- shadow IoU
- shadow contrast
- shadow consistency
- estimated overhang
- boundary adjustment direction/distance
- preliminary candidate geometry metadata
- evidence confidence
- source mode
- explicit prototype/authority disclosures

### 4. Cross-screen extraction responses

`/api/extraction/infer` and `/api/extraction/{id}` now expose `shadow_evidence` in addition to DSM/DTM elevation information.

### 5. Elevation Analysis UI

The existing Stitch/GIS/HUD layout was preserved.

The page now visibly shows:

- active sun vector
- shadow consistency
- predicted shadow length
- overhang proxy
- evidence confidence
- preliminary candidate status
- source mode
- explicit surveyor-verification disclosure

The existing decorative imagery is relabeled as illustrative rather than pretending to be the uploaded source.

### 6. API client

Added `BhuDrishtiAPI.getShadow()`.

## What is genuinely new

Before Sprint 4, the page contained a conceptual claim about using sun vectors to correct roof/parallax effects, but there was no executable shadow-analysis endpoint.

After Sprint 4, the concept is backed by a real deterministic numerical prototype that can be inspected, tested, and called by the UI.

## What Sprint 4 deliberately does NOT claim

- No trained shadow/roof ML model.
- No measured drone DSM/DTM ingestion.
- No solar ephemeris lookup.
- No verified camera calibration.
- No CRS transformation.
- No orthorectification.
- No legal parcel-boundary adjudication.
- No authoritative boundary correction.
- No production survey accuracy claim.

The current system is still a **prototype physical-evidence model**.

## Verification

```powershell
$env:PYTHONPATH="."
python backend/test_sprint2_backend_correctness.py
python backend/test_sprint3_geospatial_semantics.py
python backend/test_sprint4_differentiation.py
python -m compileall -q backend
```

Expected Sprint 4 result:

`SPRINT 4 DIFFERENTIATION: PASS`

## Judge-safe explanation

> “We have now made the shadow/parallax idea executable. We derive elevated structure from nDSM, project a first-order cast shadow from a supplied sun vector, compare it with image darkness when source pixels are available, and produce a preliminary boundary-adjustment candidate. In this prototype the elevation surface and spatial reference are still synthetic/unverified, so the candidate is evidence for a surveyor—not an authoritative cadastral correction.”
