# BhuDrishti — Sprint 2: Backend Correctness

## Objective
Make one authoritative confidence/risk calculation feed the backend surfaces consistently, and wire the existing deterministic DSM/DTM/nDSM/elevation evidence into that calculation.

## Implemented
- `confidence_engine.py` is the single weighted risk model (`sprint2-v1`).
- Topology, geometric irregularity, elevation disagreement, and historical mismatch use the same weights everywhere.
- Seeded parcels now pass through the same evaluator used by `/api/confidence`, `/api/survey-queue`, `/api/parcels`, and extraction-related responses.
- Elevation is no longer computed only for display: `overhang_offset_m` contributes to `elevation_disagreement` in the risk score.
- Historical demo shifts contribute through the same model when a seeded legacy-map value exists.
- EXT-* records use the deterministic prototype elevation surface through the same evaluator. They do not invent historical-map evidence.
- Responses expose `risk_model_version` / `risk_model` metadata so the active scoring path is inspectable.

## Known prototype boundary
The elevation dataset is still explicitly **synthetic demo elevation**, not a surveyed DSM/DTM. Sprint 2 wires the existing evidence correctly; it does not claim real-world elevation accuracy. Sprint 3 will address geospatial semantics/CRS. Sprint 4 will address actual shadow/solar-vector reasoning.

## Regression targets
- BD-047: risk **63.1**, confidence **36.9**, priority **HIGH**. Factors include topology 80.0, elevation disagreement 91.3, historical mismatch 55.0.
- BD-019: risk **18.8**, confidence **81.2**, priority **LOW**; elevation anomaly contributes to risk.
- BD-082: risk **60.0**, confidence **40.0**, priority **HIGH** from invalid/self-intersecting geometry.

Run:

```text
python backend/test_sprint2_backend_correctness.py
```

Expected:

```text
SPRINT 2 BACKEND CORRECTNESS: PASS
```
