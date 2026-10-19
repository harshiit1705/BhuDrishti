"""Regression tests for authoritative extraction persistence across app instances.

Run: python backend/test_persistence_shared_instances.py
All writes are isolated under a TemporaryDirectory; the bundled project DB/uploads
are never used or overwritten.
"""
from __future__ import annotations
import json, os, subprocess, sys, tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
with tempfile.TemporaryDirectory(prefix="bhudrishti-persistence-test-") as tmp:
    db_path = str(Path(tmp) / "shared.sqlite3")
    env = os.environ.copy()
    env.pop("VERCEL", None)
    env.pop("DATABASE_URL", None)
    env.pop("BHUDRISHTI_DATABASE_URL", None)
    env["BHUDRISHTI_DB_PATH"] = db_path
    env["PYTHONPATH"] = str(ROOT) + os.pathsep + env.get("PYTHONPATH", "")

    # Instance/process A creates an extraction and exits.
    create_script = r'''
from shapely.geometry import Polygon
from backend.app.main import app
from backend.app.database import connect_db
from backend.app.extraction_store import extraction_store, ExtractionRecord
rec = ExtractionRecord(extraction_id="EXT-0001", source_filename="orthophoto-test.png",
 geometry=Polygon([(0,0),(10,0),(10,10),(0,10)]), image_width=100, image_height=100,
 image_format="PNG", confidence_heuristic=82.0, pixel_polygon=[[0,0],[10,0],[10,10],[0,10]],
 inference_mode="test-cv", notes="isolated regression fixture", dataset_id="DS-TEST")
extraction_store.save(rec)
assert extraction_store.get("EXT-0001") is not None
with connect_db() as db:
 db.execute("INSERT INTO datasets(dataset_id,filename,file_type,size_bytes,declared_crs,status,created_at,content) VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(dataset_id) DO UPDATE SET content=excluded.content", ("DS-TEST","orthophoto-test.png","image",11,"LOCAL-DEMO","ready","2026-01-01T00:00:00Z",b"image-bytes"))
print("INSTANCE_A_CREATED")
'''
    r = subprocess.run([sys.executable, "-c", create_script], env=env, cwd=ROOT, text=True, capture_output=True)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "INSTANCE_A_CREATED" in r.stdout

    # Instance/process B sees that exact record, submits it, certifies it, and exports its geometry.
    workflow_script = r'''
from fastapi import HTTPException
from fastapi.testclient import TestClient
from backend.app import auth
from backend.app.main import app, get_extraction, submit_verification, certify_verification, export_geojson
from backend.app.extraction_store import extraction_store
from backend.app.verification_store import store
rec = extraction_store.get("EXT-0001")
assert rec is not None and rec.dataset_id == "DS-TEST"
client = TestClient(app)
token = auth.issue_token(auth.authenticate("surveyor@bhudrishti.gov.in", "Bhu@Survey2026"))
headers = {"Authorization": "Bearer " + token}
assert client.get("/api/extraction/EXT-0001", headers=headers).status_code == 200
listed = client.get("/api/extraction", headers=headers)
assert listed.status_code == 200 and any(x["extraction_id"] == "EXT-0001" for x in listed.json()["extractions"])
assert client.get("/api/extraction/EXT-MISSING-999", headers=headers).status_code == 404
source_file = client.get("/api/datasets/DS-TEST/file", headers=headers)
assert source_file.status_code == 200 and source_file.content == b"image-bytes"
health = client.get("/api/health")
assert health.status_code == 200 and health.json()["persistence"]["connected"] is True
status = client.get("/api/system/status", headers=headers)
assert status.status_code == 200 and status.json()["persistence"]["connected"] is True
response = submit_verification("EXT-0001", {"geometry":{"type":"Polygon","coordinates":[[[1,1],[9,1],[9,9],[1,9],[1,1]]]},"statement":"cross-instance review"}, {"name":"Test Surveyor","role":"FIELD_SURVEYOR"})
assert response["verification"]["status"] == "in_review"
certified = certify_verification("EXT-0001", {}, {"name":"Test Surveyor","role":"FIELD_SURVEYOR"})
assert certified["verification"]["status"] == "verified"
assert store.get("EXT-0001").verified_geometry.area == 64
out = export_geojson({"name":"Test Surveyor","role":"FIELD_SURVEYOR"})
feature = next(f for f in out["features"] if f["properties"]["parcel_id"] == "EXT-0001")
assert feature["properties"]["verification_status"] == "verified"
assert round(__import__('shapely.geometry', fromlist=['shape']).shape(feature['geometry']).area, 2) == 64
try:
    get_extraction("EXT-MISSING-999")
except HTTPException as e:
    assert e.status_code == 404 and "Extraction record not found" in str(e.detail)
else:
    raise AssertionError("missing extraction must return a truthful 404")
print("INSTANCE_B_LOAD_FILE_BYTES_SUBMIT_CERTIFY_EXPORT_AND_HEALTH_PASS")
'''
    r = subprocess.run([sys.executable, "-c", workflow_script], env=env, cwd=ROOT, text=True, capture_output=True)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "INSTANCE_B_LOAD_FILE_BYTES_SUBMIT_CERTIFY_EXPORT_AND_HEALTH_PASS" in r.stdout

    # The Vercel runtime must fail closed instead of silently selecting /tmp.
    fail_script = "import backend.app.persistence"
    fail_env = env.copy(); fail_env["VERCEL"] = "1"; fail_env.pop("BHUDRISHTI_ALLOW_EPHEMERAL_SQLITE", None)
    fail_env.pop("BHUDRISHTI_DB_PATH", None)
    r = subprocess.run([sys.executable, "-c", fail_script], env=fail_env, cwd=ROOT, text=True, capture_output=True)
    assert r.returncode != 0 and "requires managed PostgreSQL on Vercel" in (r.stdout + r.stderr)
    # A PostgreSQL DSN is accepted as configuration; app import must attempt a real
    # connection rather than falsely claiming the adapter is connected.
    pg_env = fail_env.copy(); pg_env["DATABASE_URL"] = "postgresql://invalid.invalid:5432/not_a_real_db"
    pg_env["BHUDRISHTI_AUTH_SECRET"] = "test-secret-for-import-only"
    r = subprocess.run([sys.executable, "-c", "import backend.app.main"], env=pg_env, cwd=ROOT, text=True, capture_output=True)
    assert r.returncode != 0 and "does not include a PostgreSQL repository adapter" not in (r.stdout + r.stderr)

    # All HTML pages share the API client; production frontend/backend proxy declarations match.
    api_client = (ROOT / "frontend" / "js" / "api-client.js").read_text(encoding="utf-8")
    field_page = (ROOT / "frontend" / "field-verification.html").read_text(encoding="utf-8")
    netlify = (ROOT / "frontend" / "netlify.toml").read_text(encoding="utf-8")
    redirects = (ROOT / "frontend" / "_redirects").read_text(encoding="utf-8")
    vercel = (ROOT / "vercel.json").read_text(encoding="utf-8")
    assert "return apiRequest(`/api/extraction/${encodeURIComponent(extractionId)}`)" in api_client
    assert "getExtraction(targetId).catch(()=>getWorkflowExtraction(targetId))" not in field_page
    assert "https://bhudrishti-api.vercel.app/api/:splat" in redirects and 'publish = "."' in netlify
    assert '"src": "api/index.py"' in vercel and '"dest": "api/index.py"' in vercel
    assert (ROOT / "api" / "index.py").is_file()

print("SHARED INSTANCE PERSISTENCE + API GET/404 + SUBMIT/CERTIFY/EXPORT: PASS")
print("VERCEL MANAGED DATABASE CONFIG FAIL-FAST + NO SQLITE FALLBACK: PASS")
