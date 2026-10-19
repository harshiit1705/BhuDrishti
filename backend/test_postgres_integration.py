"""Opt-in real PostgreSQL integration test, skipped unless BHUDRISHTI_TEST_DATABASE_URL is set.

Run: BHUDRISHTI_TEST_DATABASE_URL='postgresql://...' python backend/test_postgres_integration.py
Use a disposable test database. It verifies independent-process persistence, DB-backed
orthophoto bytes, verification transitions/audit, export, queue, and truthful health.
"""
from __future__ import annotations
import os, subprocess, sys, uuid
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
DSN=os.environ.get("BHUDRISHTI_TEST_DATABASE_URL", "").strip()
if not DSN:
    print("POSTGRES INTEGRATION: SKIP (BHUDRISHTI_TEST_DATABASE_URL not configured; no live database was tested)")
    raise SystemExit(0)
record_id="EXT-PGTEST-"+uuid.uuid4().hex[:12].upper()
dataset_id="DS-PGTEST-"+uuid.uuid4().hex[:10].upper()
env=os.environ.copy(); env["DATABASE_URL"]=DSN; env["BHUDRISHTI_AUTH_SECRET"]=env.get("BHUDRISHTI_AUTH_SECRET", "pg-integration-test-secret-only-32-bytes-minimum")
env.pop("VERCEL",None); env["PYTHONPATH"]=str(ROOT)+os.pathsep+env.get("PYTHONPATH","")
create=f'''from shapely.geometry import Polygon
from backend.app.main import app
from backend.app.database import connect_db
from backend.app.extraction_store import extraction_store, ExtractionRecord
rec=ExtractionRecord(extraction_id={record_id!r},source_filename="pg-test.png",geometry=Polygon([(0,0),(10,0),(10,10),(0,10)]),image_width=64,image_height=64,image_format="PNG",confidence_heuristic=80,pixel_polygon=[[0,0],[10,0],[10,10],[0,10]],inference_mode="pg-test",notes="integration",dataset_id={dataset_id!r})
extraction_store.save(rec)
with connect_db() as db: db.execute("INSERT INTO datasets(dataset_id,filename,file_type,size_bytes,declared_crs,status,created_at,content) VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(dataset_id) DO UPDATE SET content=excluded.content",({dataset_id!r},"pg-test.png","image",10,"LOCAL-DEMO","ready","2026-01-01T00:00:00Z",b"pg-bytes"))
print("PG_INSTANCE_A_PASS")'''
load=f'''from fastapi.testclient import TestClient
from backend.app.main import app, submit_verification, certify_verification, export_geojson
from backend.app.auth import authenticate, issue_token
from backend.app.extraction_store import extraction_store
from backend.app.verification_store import store
from backend.app.database import check_database
rid={record_id!r}; did={dataset_id!r}
rec=extraction_store.get(rid); assert rec and rec.dataset_id==did
client=TestClient(app)
assert client.get("/api/health").json()["persistence"]["connected"] is True
token=issue_token(authenticate("surveyor@bhudrishti.gov.in","Bhu@Survey2026")); headers={{"Authorization":"Bearer "+token}}
assert client.get("/api/system/status").json()["persistence"]["connected"] is True
file=client.get(f"/api/datasets/{{did}}/file",headers=headers); assert file.status_code==200 and file.content==b"pg-bytes"
sub=submit_verification(rid,{{"geometry":{{"type":"Polygon","coordinates":[[[1,1],[9,1],[9,9],[1,9],[1,1]]]}},"statement":"PG integration"}},{{"name":"PG Test Surveyor","role":"FIELD_SURVEYOR"}}); assert sub["verification"]["status"]=="in_review"
cert=certify_verification(rid,{{}},{{"name":"PG Test Surveyor","role":"FIELD_SURVEYOR"}}); assert cert["verification"]["status"]=="verified"
assert len(store.get(rid).audit_trail)>=3
feature=next(f for f in export_geojson({{"name":"PG Test Surveyor","role":"FIELD_SURVEYOR"}})["features"] if f["properties"]["parcel_id"]==rid)
assert feature["properties"]["verification_status"]=="verified"
queue=client.get("/api/survey-queue",headers=headers); assert queue.status_code==200
assert any(x.get("parcel_id")==rid for x in queue.json()["queue"])
with __import__('backend.app.database',fromlist=['connect_db']).connect_db() as db:
 db.execute("DELETE FROM verifications WHERE parcel_id=?",(rid,)); db.execute("DELETE FROM extractions WHERE extraction_id=?",(rid,)); db.execute("DELETE FROM datasets WHERE dataset_id=?",(did,))
print("PG_INSTANCE_B_FILE_SUBMIT_CERTIFY_AUDIT_EXPORT_QUEUE_HEALTH_PASS")'''
try:
    for label,script in (("instance A",create),("instance B",load)):
        result=subprocess.run([sys.executable,"-c",script],cwd=ROOT,env=env,text=True,capture_output=True)
        if result.returncode:
            raise RuntimeError(f"{label} failed:\n{result.stdout}\n{result.stderr}")
        print(result.stdout.strip())
finally:
    # Best-effort cleanup if process B fails before its own cleanup block.
    cleanup=f'''from backend.app.database import connect_db
with connect_db() as db:
 db.execute("DELETE FROM verifications WHERE parcel_id=?",({record_id!r},)); db.execute("DELETE FROM extractions WHERE extraction_id=?",({record_id!r},)); db.execute("DELETE FROM datasets WHERE dataset_id=?",({dataset_id!r},))'''
    subprocess.run([sys.executable,"-c",cleanup],cwd=ROOT,env=env,text=True,capture_output=True)
