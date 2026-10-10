# Sprint 7 — Active Orthophoto Rendering

## Problem fixed
The EXT workflow could display a selected `EXT-*` label while the Topology and Elevation pages still showed hardcoded Stitch demo maps and charts. Those visuals could mislead users into believing they described the uploaded image.

## Behavior
- When `topology-validation.html?parcel=EXT-...` is opened, the seeded BD map is replaced immediately, before asynchronous requests. The page then renders the original image associated with that extraction and overlays its pixel candidate boundary when available.
- When `elevation-analysis.html?parcel=EXT-...` is opened, the illustrative ORI, pseudo-color DEM, and static cross-section are replaced before asynchronous requests. The same source orthophoto and candidate outline are shown; the page explicitly states that an orthophoto is not a real DSM/DTM and cannot yield a real elevation profile by itself.
- The source image is recovered from the browser's extraction-image cache first, then the dataset-image cache, then the authenticated dataset file endpoint.
- If the source image cannot be recovered, an explicit unavailable message is shown. The page does not fall back to unrelated demo imagery for an active EXT record.
- BD seeded views remain available when the user has not selected an EXT record.
- For un-georeferenced EXT uploads, cross-parcel overlap/gap statistics are marked not calculated instead of displaying seeded parcel statistics.

## Verification
- Inline JavaScript syntax checked for all HTML pages.
- Sprint 2 backend correctness regression passed.
- Sprint 3 geospatial semantics regression passed.
- Sprint 4 differentiation regression passed.
- These checks do not replace a manual browser test of upload → extraction → GIS → topology → elevation → GIS.

## Limitation
The image-derived candidate polygon is in image pixel coordinates. It is not a georeferenced cadastral boundary. No real DSM/DTM or image-derived height profile is fabricated when none is uploaded.
