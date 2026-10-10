# BhuDrishti — Sprint 3: Geospatial Correctness

## Goal
Make the prototype's coordinate reference, GSD, geometry-area, and export semantics explicit so local/demo geometry is never presented as authoritative georeferenced cadastral data.

## Implemented
- Added explicit coordinate metadata to backend responses:
  - `crs`
  - `declared_crs`
  - `crs_status`
  - `georeferenced`
  - `units`
  - `area_semantics`
  - `gsd_m_per_pixel`
  - `gsd_status`
- `LOCAL-DEMO` is explicitly `NOT_GEOREFERENCED`.
- A supplied `EPSG:<code>` is recorded as `DECLARED_NOT_VERIFIED`; the prototype does not claim that it transformed or verified the imagery.
- Geometry semantics distinguish preliminary AI geometry from authoritative cadastral geometry.
- GeoJSON export now carries explicit per-feature spatial/area semantics and clearly states that the current export is not georeferenced.
- Dataset validation no longer claims support for LAS/LAZ/GeoJSON/Shapefile in the current CV inference path.
- Frontend static coordinate/GSD/area labels were changed to explicit LOCAL-DEMO / not-verified wording while preserving the existing Stitch/GIS UI.
- Survey Projects upload selector now reflects formats actually supported by the current image inference path.

## Important limitation
This sprint does **not** implement a real orthophoto georeferencing transform, CRS reprojection, sensor-derived GSD extraction, or PostGIS. A declared CRS is metadata only until a real geospatial reader/transform pipeline is added.

## Verification
Run from the repository root:

```powershell
python backend/test_sprint2_backend_correctness.py
python backend/test_sprint3_geospatial_semantics.py
```

Expected final lines:

```text
SPRINT 2 BACKEND CORRECTNESS: PASS
SPRINT 3 GEOSPATIAL SEMANTICS: PASS
```
