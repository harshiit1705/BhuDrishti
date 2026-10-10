# Sprint 6 — Active orthophoto rendering guard

For an active `EXT-*`, Topology Validation and Elevation Analysis replace their static Stitch demonstration map/section with the selected extraction's browser-cached image (or dataset file endpoint) and the selected extraction's pixel polygon. The topology page explicitly states that cross-parcel topology is not calculated for a single non-georeferenced upload. Elevation explicitly distinguishes synthetic API values from a real DSM/DTM and disables the decorative cross-section for EXT records. Seeded BD views remain for intentional BD selections.

Limitations: if the browser cache and dataset file endpoint are unavailable, the page shows a geometry-only placeholder. This does not add georeferencing or real elevation rasters.
