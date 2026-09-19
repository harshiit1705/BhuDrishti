# BhuDrishti End-to-End Workflow Upgrade

## Goal
Connect the existing Stitch UI into one persistent prototype workflow:
Dashboard → Dataset → AI Extraction → GIS → Topology/Elevation → Survey Priority → Field Verification → Certification → Export.

## Implemented
- SQLite persistence for AI extraction and HITL verification state. Records survive page navigation, refresh, and backend restart.
- Dataset upload endpoint with persistent dataset metadata and local file storage for prototype inputs.
- Dataset → AI inference endpoint (`POST /api/datasets/{dataset_id}/infer`).
- Survey Projects upload action now creates a backend dataset and starts AI Extraction with that dataset.
- EXT-* extraction records can enter Field Verification, be corrected, submitted, certified/rejected, and retain an audit trail.
- Verified EXT-* geometry becomes authoritative for downstream export.
- GeoJSON export now includes seeded parcels and persisted AI extraction records.
- Elevation endpoint accepts EXT-* records using a clearly labelled deterministic synthetic prototype surface.
- Survey Priority Verify action opens the same EXT-* record in Field Verification.
- Added dashboard.html compatibility entry point because existing navigation referenced it while the compact package contained index.html.

## Truthfulness
No real CRS/georeferencing, government system integration, GNSS, trained segmentation model, or production cadastral certification is claimed. Elevation remains synthetic prototype data.

## Verification
- Python compile check passed.
- API smoke tests passed for system status, dataset upload, dataset inference, extraction persistence after restart, EXT verification submit/certify, survey queue, and export.
- Frontend inline JavaScript syntax check passed.
