# Active orthophoto workflow repair

## Findings from the supplied archive

- Survey Projects persisted the selected image in IndexedDB keyed by dataset ID, but a newly uploaded dataset did not clear the previous extraction ID. The old EXT context could therefore travel into the new workflow.
- Topology and Elevation renderers already replaced seeded visual panels for EXT records, but image selection could borrow the latest dataset when an extraction lacked `dataset_id`. That could associate an explicitly selected historical extraction with an unrelated recent upload.
- The active EXT renderers awaited backend/cache calls without rechecking whether the user had selected another extraction while those calls were in flight.
- The dataset file endpoint was served without the same role-based access dependency used for upload/inference.
- The project is configured to use a local SQLite/filesystem store in local development and `/tmp/bhudrishti` in serverless mode. `/tmp` is ephemeral; it must not be treated as durable cross-instance storage in production.

## Changes

- `frontend/survey-projects.html`: a successfully accepted upload clears the old active extraction; starting inference no longer carries an extraction belonging to another dataset.
- `frontend/topology-validation.html` and `frontend/elevation-analysis.html`: image resolution is strictly tied to the selected extraction's `dataset_id`, and stale asynchronous responses are discarded if the active extraction changes.
- `backend/app/main.py`: dataset file retrieval now requires an authenticated role permitted to access uploaded datasets.
- `backend/test_active_orthophoto_rendering.py`: regression guards cover source-image rendering contracts, dataset/extraction association, and stale-response handling.

## State and image contract

- Dataset identity and original bytes: backend dataset registry plus filesystem upload in local mode; browser IndexedDB stores a dataset-ID-keyed File as a same-browser continuity fallback.
- Extraction identity and geometry: backend extraction record, including its `dataset_id`; browser localStorage caches extraction records only as an offline continuity fallback.
- Topology/Elevation choose the requested extraction first, retrieve its own `dataset_id`, then use its dataset-keyed browser File or authenticated backend file endpoint. They do not substitute the latest unrelated dataset.
- On EXT views, seeded visuals are replaced before asynchronous loading; missing imagery is an explicit unavailable state, not a seeded-map fallback. BD demo content remains available through explicit seeded selection.

## Verification performed

- `backend/test_active_orthophoto_rendering.py`: PASS.
- `backend/test_sprint2_backend_correctness.py`: PASS.
- `backend/test_sprint3_geospatial_semantics.py`: PASS.
- `backend/test_sprint4_differentiation.py`: PASS.
- Python compile check for backend app and tests: PASS.
- Node syntax checks for 30 inline frontend scripts: PASS.
- Browser end-to-end screenshots and the full A-to-B upload workflow were **not verified** in this repair run. Therefore visual behavior across all pages, login/session integration, browser back/forward, and real multi-instance deployment remain unverified; source-level tests are not a substitute for those checks.

## Deployment limitation

The serverless configuration uses an ephemeral `/tmp` storage path. Production deployments requiring uploads to survive instance changes must configure a shared persistent object store or persistent volume/database and ensure the dataset registry and image bytes share that durable backing store. This repair does not add a new infrastructure provider.
