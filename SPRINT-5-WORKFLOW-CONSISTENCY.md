# Sprint 5 — End-to-End Workflow Consistency

## Problem fixed

The same uploaded orthophoto could appear to disappear after returning to Survey Projects, while Topology Validation or Elevation Analysis could appear to show a different seeded/demo record.

## Changes

- Active EXT-* extraction ID is persisted in both sessionStorage and localStorage.
- `setLatestExtractionId()` immediately reapplies shared sidebar navigation after an extraction is created. This fixes the race where the sidebar had already rendered its original seeded links before EXT-* existed.
- Sidebar links for GIS, Topology, Elevation, Survey Priority and Survey Projects now carry the active workflow context.
- Active dataset ID is persisted separately and Survey Projects restores its cached dataset metadata immediately.
- Survey Projects no longer clears the visible selected upload just because `/api/datasets` is temporarily served by a different serverless instance.
- AI Feature Extraction can restore the selected dataset from browser-local metadata and IndexedDB image storage.
- EXT-* topology, elevation and shadow API helpers use the exact cached EXT record as a continuity fallback when a serverless backend instance cannot see that record. They never substitute seeded BD-* data.
- The shared topology badge is scoped to the active EXT-* record when one exists rather than showing the global seeded issue count.
- The backend remains the source of truth whenever the requested EXT-* record is available there.

## Expected workflow

Survey Projects → upload orthophoto → AI Feature Extraction → EXT-XXXX → GIS → Topology → Elevation → GIS → Survey Projects

The same EXT-XXXX and the same uploaded image should remain selected throughout the browser session.

## Important prototype limitation

Uploaded orthophotos remain non-georeferenced local/demo imagery. Elevation and shadow evidence remain synthetic/physics-inspired prototype analysis. Seeded BD-* records are still available when explicitly opened without an active uploaded workflow.
