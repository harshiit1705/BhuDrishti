"""Certification API regressions, isolated from project/user data."""
from __future__ import annotations
import os, subprocess, sys, tempfile
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]

CHILD = r'''
import sys
from pathlib import Path
sys.path.insert(0, str(Path.cwd()))
from fastapi.testclient import TestClient
from shapely.geometry import Polygon
from backend.app import auth
from backend.app.extraction_store import ExtractionRecord, extraction_store
from backend.app.main import app, store

def poly(coords):
    ring=[list(p) for p in coords]
    if ring[0] != ring[-1]: ring.append(ring[0])
    return {"type":"Polygon","coordinates":[ring]}

ai=Polygon([(0,0),(10,0),(10,10),(0,10)])
def add(pid):
    extraction_store.save(ExtractionRecord(extraction_id=pid,source_filename="isolated-test.png",geometry=ai,
        image_width=100,image_height=100,image_format="PNG",confidence_heuristic=80,
        pixel_polygon=[[0,0],[100,0],[100,100],[0,100]],inference_mode="test",notes="fixture",dataset_id="DS-TEST"))

def token(email,pw): return auth.issue_token(auth.authenticate(email,pw))
surveyor=token("surveyor@bhudrishti.gov.in","Bhu@Survey2026")
admin=token("admin@bhudrishti.gov.in","Bhu@Admin2026")
gis=token("gis@bhudrishti.gov.in","Bhu@GIS2026")
def h(t): return {"Authorization":"Bearer "+t}
client=TestClient(app)
pid="EXT-CERT-1001"; add(pid)
corrected=poly([(1,1),(12,1),(12,9),(1,9)])
assert client.get(f"/api/verification/{pid}",headers=h(surveyor)).json()["status"]=="unverified"
r=client.post(f"/api/verification/{pid}/submit",headers=h(surveyor),json={"geometry":corrected,"statement":"review","surveyor_license":"TEST"})
assert r.status_code==200 and r.json()["verification"]["status"]=="in_review",r.text
assert extraction_store.get(pid).status=="in_review"
r=client.post(f"/api/verification/{pid}/certify",headers=h(surveyor),json={})
assert r.status_code==200 and r.json()["verification"]["status"]=="verified",r.text
before=client.get(f"/api/verification/{pid}",headers=h(surveyor)).json()
r=client.post(f"/api/verification/{pid}/certify",headers=h(surveyor),json={})
after=r.json()["verification"]
assert r.status_code==200 and after["audit_trail"]==before["audit_trail"] and after["verified_geometry"]==before["verified_geometry"]
assert extraction_store.get(pid).status=="verified"
print("PASS submit -> certify; repeat certification preserves audit and geometry")

pid2="EXT-CERT-1002"; add(pid2)
assert client.post(f"/api/verification/{pid2}/submit",headers=h(surveyor),json={"geometry":corrected,"statement":"review"}).status_code==200
assert client.post(f"/api/verification/{pid2}/reject",headers=h(surveyor),json={"reason":"fix"}).status_code==200
assert client.post(f"/api/verification/{pid2}/certify",headers=h(surveyor),json={}).status_code==409
assert client.post(f"/api/verification/{pid2}/submit",headers=h(surveyor),json={"geometry":corrected,"statement":"resubmitted"}).status_code==200
assert client.post(f"/api/verification/{pid2}/certify",headers=h(surveyor),json={}).status_code==200
print("PASS rejected -> certification denied until correction is resubmitted")

pid3="EXT-CERT-1003"; add(pid3)
assert client.post(f"/api/verification/{pid3}/accept-preliminary",headers=h(surveyor),json={}).status_code==403
assert client.post(f"/api/verification/{pid3}/accept-preliminary",headers=h(admin),json={}).status_code==200
assert client.post(f"/api/verification/{pid3}/certify",headers=h(gis),json={}).status_code==403
assert client.post(f"/api/verification/{pid}/certify",json={}).status_code==401
print("PASS role authorization and unauthenticated access denial")

out=client.get("/api/export/geojson",headers=h(surveyor))
assert out.status_code==200,out.text
feature=next(f for f in out.json()["features"] if f["properties"]["parcel_id"]==pid)
assert feature["properties"]["verification_status"]=="verified"
assert Polygon(feature["geometry"]["coordinates"][0]).equals(Polygon([(1,1),(12,1),(12,9),(1,9)]))
print("PASS export contains certified geometry and status")
'''

if __name__ == "__main__":
    with tempfile.TemporaryDirectory(prefix="bhudrishti-certification-") as temp:
        env=os.environ.copy(); env.pop("VERCEL",None); env.pop("DATABASE_URL",None); env.pop("BHUDRISHTI_DATABASE_URL",None)
        env["BHUDRISHTI_DB_PATH"]=str(Path(temp)/"certification.sqlite3")
        env["PYTHONPATH"]=str(ROOT)+os.pathsep+env.get("PYTHONPATH","")
        result=subprocess.run([sys.executable,"-c",CHILD],cwd=ROOT,env=env,text=True,capture_output=True)
        print(result.stdout,end="")
        if result.returncode:
            print(result.stderr,file=sys.stderr)
            raise SystemExit(result.returncode)
        print("CERTIFICATION WORKFLOW REGRESSION: PASS (isolated shared SQLite)")
