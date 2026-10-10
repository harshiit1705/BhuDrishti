# BhuDrishti End-to-End Workflow Fix

## Workflow covered
Survey Projects → AI Feature Extraction → GIS Cadastral Map → Survey Priority → Field Verification → Certification → Export Cadastre.

## What was fixed
- The uploaded ORI File is kept in browser IndexedDB so the next page does not depend on Vercel `/tmp` storage.
- The completed `EXT-*` extraction response is stored in browser-local workflow state so GIS, Survey Priority, Field Verification, and Export can continue even when a later Vercel invocation lands on another serverless instance.
- Survey Priority merges the current browser workflow extraction into the backend queue and shows AI/CV confidence separately from survey risk.
- GIS loads an `EXT-*` record from the backend first and falls back to the browser workflow record when serverless persistence is unavailable.
- Field Verification loads the same `EXT-*` geometry and ORI, saves edits as `in_review`, and certifies as `verified`. Backend calls are attempted first; browser workflow state is retained as the demo continuity layer when serverless persistence is unavailable.
- Certification accepts the preliminary geometry when no edit has been submitted yet, preventing a dead-end `unverified -> certify` action.
- Export uses verified geometry when available and can generate a browser-local GeoJSON fallback for the active extraction.
- The package excludes the local SQLite database and Python bytecode so stale runtime state is not shipped to Vercel.

## Prototype persistence disclosure
Vercel serverless local filesystem storage is not durable shared storage. Browser-local workflow state is therefore used for this SIH prototype's cross-screen demo continuity. For production, replace this with managed database/object storage.
