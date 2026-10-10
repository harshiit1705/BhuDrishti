"""Sprint 3 geospatial semantics regression checks.
Run from repo root: python backend/test_sprint3_geospatial_semantics.py
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.app.main import _coordinate_system, _geometry_semantics, validate_dataset

local = _coordinate_system()
assert local["crs"] is None
assert local["georeferenced"] is False
assert local["crs_status"] == "NOT_GEOREFERENCED"
assert local["area_semantics"] == "LOCAL_DEMO_SQUARE_METRES"
assert local["gsd_status"] == "DEMO_CONSTANT_NOT_SENSOR_METADATA"
assert _geometry_semantics(local, "ai_extraction")["authoritative"] is False

declared = _coordinate_system("EPSG:32643", source="dataset:DS-TEST")
assert declared["crs"] == "EPSG:32643"
assert declared["georeferenced"] is False
assert declared["crs_status"] == "DECLARED_NOT_VERIFIED"
assert declared["units"] == "unknown_until_crs_verified"
assert _geometry_semantics(declared, "ai_extraction")["authoritative"] is False

ok = validate_dataset({"file_type": "geotiff", "declared_crs": "EPSG:32643"})
assert ok["valid"] is True, ok
assert ok["coordinate_system"]["crs_status"] == "DECLARED_NOT_VERIFIED"

bad = validate_dataset({"file_type": "las", "declared_crs": "LOCAL-DEMO"})
assert bad["valid"] is False, bad
assert any("Unsupported for current inference pipeline" in e for e in bad["errors"])

print("SPRINT 3 GEOSPATIAL SEMANTICS: PASS")
print("LOCAL-DEMO:", local)
print("DECLARED EPSG:", declared)
