# BhuDrishti — HITL / Export Workflow Fix

## Fixed

- GIS `EXT-*` records can now open Field Verification; the previous code explicitly disabled the button for extraction records.
- Field Verification now loads the same persisted EXT record and, for dataset-backed extractions, displays the same uploaded ORI rather than the decorative Stitch map.
- EXT field editing uses the extraction pixel geometry against the source image and converts edits back into the persisted local-demo geometry for backend verification.
- Verified geometry is reloaded as the authoritative boundary when a record has already been certified.
- GIS → Field Verification preserves the selected `EXT-*` target.
- `Sign & Certify Boundary` now navigates directly to `export-cadastre.html?parcel=EXT-XXXX` after successful backend certification.
- Export Cadastre is query-aware for `EXT-*`: it displays the selected uploaded ORI, extracted parcel candidates, roof footprints, and current authoritative boundary instead of the static cadastral SVG.
- Export download is scoped to the selected EXT record when the page is opened with `?parcel=EXT-XXXX`.
- Export metrics become selected-record metrics on a targeted export page; the global page remains available without a query parameter.
- Removed a duplicate `const EXTRACTION_IMAGE_STORE` declaration that could prevent `api-client.js` from parsing in browsers.

## Verified

- Python backend compilation passes.
- All frontend inline JavaScript blocks pass `node --check` extraction/syntax validation.
- Runtime smoke test: dataset upload → EXT inference → verification submit → certification → GeoJSON export.
- Runtime export contains the certified EXT record with `source=surveyor_verified` and `verification_status=verified`.

## Prototype limitations

- Uploaded imagery remains local-demo and not georeferenced.
- Classical OpenCV extraction is a prototype, not a trained cadastral model.
- DSM/DTM analysis remains synthetic unless real elevation data is supplied and processed by a real raster pipeline.
- Export is GeoJSON-backed prototype output; government/NIC-eSign/SVAMITVA integrations are not connected.
