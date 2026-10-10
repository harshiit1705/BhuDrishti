# GIS Orthophoto Layer Fix

## What changed

- Dataset-backed EXT-* records now load the exact persisted ORI from `/api/datasets/{dataset_id}/file` when the browser's IndexedDB copy is unavailable.
- GIS never falls back to the decorative Stitch demo map for an uploaded extraction.
- All persisted image-derived parcel candidates are rendered over the uploaded orthophoto.
- All persisted prototype roof footprints are rendered and labelled.
- Candidate-level topology checks (invalid/self-intersection and overlap in image pixel space) are returned with the extraction and can be visualized in GIS.
- GIS shows a source banner with dataset ID, filename, candidate count, roof count and topology flags.
- If the source image cannot be rendered, GIS shows an explicit source-unavailable panel instead of silently showing demo imagery.

## Important prototype limitation

An ORI image by itself does not contain legally authoritative cadastral boundaries or resident records. The current OpenCV engine derives preliminary image-space candidates and prototype roof footprints from the pixels. They are not legal parcel boundaries and are not georeferenced. A production system would replace/augment this stage with a trained building/parcel segmentation model plus verified GIS/ground-control layers.
