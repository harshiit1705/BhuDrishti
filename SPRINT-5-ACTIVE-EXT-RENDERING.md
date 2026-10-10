# Sprint 5 — Active EXT Rendering Fix

## Problem addressed
The active `EXT-*` identifier was being carried in the URL, but Topology Validation still rendered the seeded BD map and Elevation Analysis still rendered a decorative orthophoto, synthetic static DEM graphic, and hardcoded cross-section.

## Changes
- Added `getWorkflowOrthophotoUrl(record)` to the shared frontend API client. It resolves the exact extraction image from browser IndexedDB, then the dataset image cache, then the authenticated dataset-file endpoint.
- For an active `EXT-*`, Topology Validation immediately suppresses the seeded map while loading, then displays the selected extraction's source image and image-pixel candidate polygon. It no longer shows the BD-042/BD-047/BD-103/BD-082 map in this mode.
- For an active `EXT-*`, Topology Validation changes zone-level historical and road-network statistics to “Not evaluated” because the uploaded image has no verified CRS alignment to those seeded layers.
- For an active `EXT-*`, Elevation Analysis immediately suppresses the static demonstration image/DEM panel and decorative cross-section. It displays the same uploaded image with the candidate polygon and a record-specific summary of synthetic prototype elevation outputs.
- If the source image cannot be recovered, the pages show a missing-image message rather than silently falling back to a demo image.
- `BD-*` navigation retains the seeded demo workflow.

## Verification
- JavaScript syntax check across frontend inline scripts: PASS
- Shared API client syntax check: PASS
- Sprint 2 backend correctness regression: PASS
- Sprint 3 geospatial semantics regression: PASS
- Sprint 4 differentiation regression: PASS
- ZIP integrity: checked after packaging

## Limitations
- EXT geometry is image-pixel/local-demo geometry, not a verified georeferenced cadastral boundary.
- EXT elevation metrics remain synthetic prototype outputs. No real DSM/DTM raster is attached to the orthophoto.
- Cross-parcel topology against seeded BD parcels is intentionally not reported for non-georeferenced EXT uploads.
