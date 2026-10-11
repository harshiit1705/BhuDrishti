"""Isolated certification state-machine/API regression tests.

Run from the project root: python backend/test_certification_workflow.py
All SQLite stores are redirected to a temporary directory; project databases are untouched.
"""
from __future__ import annotations
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient
from shapely.geometry import Polygon, mapping

from app import auth, extraction_store as extraction_store_module, verification_store as verification_store_module
from app.extraction_store import ExtractionRecord
from app.main import app, extraction_store, store


def _polygon(coords):
    return {"type": "Polygon", "coordinates": [[list(p) for p in coords + [coords[0]]]]}


def _geometry(coords):
    return Polygon(coords)


def run_tests():
    with tempfile.TemporaryDirectory(prefix="bhudrishti-cert-tests-") as temp:
        tmp = Path(temp)
        verification_store_module.DB_PATH = tmp / "verification.sqlite3"
        extraction_store_module.DB_PATH = tmp / "extractions.sqlite3"
        auth._db_path = lambda: tmp / "auth.sqlite3"
        # Reinitialize schema against isolated paths.
        verification_store_module.PersistentVerificationRepository()
        extraction_store_module.PersistentExtractionRepository()
        auth.ensure_demo_users()

        def token(email, password):
            return auth.issue_token(auth.authenticate(email, password))

        surveyor = token("surveyor@bhudrishti.gov.in", "Bhu@Survey2026")
        admin = token("admin@bhudrishti.gov.in", "Bhu@Admin2026")
        gis = token("gis@bhudrishti.gov.in", "Bhu@GIS2026")
        client = TestClient(app)

        # An EXT record is necessary to exercise the same geometry resolver and export path.
        pid = "EXT-9876"
        ai = Polygon([(0, 0), (10, 0), (10, 10), (0, 10)])
        extraction_store.save(ExtractionRecord(
            extraction_id=pid, source_filename="cert-test.png", geometry=ai,
            image_width=100, image_height=100, image_format="PNG", confidence_heuristic=80,
            pixel_polygon=[[0, 0], [100, 0], [100, 100], [0, 100]],
            inference_mode="test", notes="isolated certification test", dataset_id="DS-CERT-TEST"
        ))

        def headers(tok):
            return {"Authorization": f"Bearer {tok}"}

        # A: unverified -> submitted review -> verified.
        get0 = client.get(f"/api/verification/{pid}", headers=headers(surveyor))
        assert get0.status_code == 200 and get0.json()["status"] == "unverified", get0.text
        corrected = _polygon([(1, 1), (12, 1), (12, 9), (1, 9)])
        submitted = client.post(f"/api/verification/{pid}/submit", headers=headers(surveyor), json={
            "geometry": corrected, "statement": "Correction reviewed for certification.", "surveyor_license": "TEST-LIC"
        })
        assert submitted.status_code == 200, submitted.text
        assert submitted.json()["verification"]["status"] == "in_review"
        assert extraction_store.get(pid).status == "in_review"
        certified = client.post(f"/api/verification/{pid}/certify", headers=headers(surveyor), json={})
        assert certified.status_code == 200, certified.text
        rec = certified.json()["verification"]
        assert rec["status"] == "verified"
        assert Polygon(rec["verified_geometry"]["coordinates"][0]).equals(_geometry([(1, 1), (12, 1), (12, 9), (1, 9), (1, 1)]))
        assert extraction_store.get(pid).status == "verified"
        print("PASS unverified -> in_review -> verified")

        # B: repeat certification is idempotent and leaves geometry/audit unchanged.
        before = client.get(f"/api/verification/{pid}", headers=headers(surveyor)).json()
        repeat = client.post(f"/api/verification/{pid}/certify", headers=headers(surveyor), json={})
        assert repeat.status_code == 200, repeat.text
        after = repeat.json()["verification"]
        assert after["status"] == "verified"
        assert after["audit_trail"] == before["audit_trail"]
        assert after["verified_geometry"] == before["verified_geometry"]
        assert extraction_store.get(pid).status == "verified"
        print("PASS verified -> repeated certify is idempotent; no duplicate audit/geometry change")

        # C: rejected record cannot certify; correction submission is required first.
        pid_rej = "EXT-9877"
        extraction_store.save(ExtractionRecord(
            extraction_id=pid_rej, source_filename="rejected-test.png", geometry=ai,
            image_width=100, image_height=100, image_format="PNG", confidence_heuristic=70,
            pixel_polygon=[[0, 0], [100, 0], [100, 100], [0, 100]],
            inference_mode="test", notes="rejection test", dataset_id="DS-CERT-TEST"
        ))
        assert client.post(f"/api/verification/{pid_rej}/submit", headers=headers(surveyor), json={"geometry": corrected, "statement": "review"}).status_code == 200
        rejected = client.post(f"/api/verification/{pid_rej}/reject", headers=headers(surveyor), json={"reason": "Needs correction"})
        assert rejected.status_code == 200 and rejected.json()["verification"]["status"] == "rejected"
        denied = client.post(f"/api/verification/{pid_rej}/certify", headers=headers(surveyor), json={})
        assert denied.status_code == 409, denied.text
        assert client.get(f"/api/verification/{pid_rej}", headers=headers(surveyor)).json()["status"] == "rejected"
        resubmitted = client.post(f"/api/verification/{pid_rej}/submit", headers=headers(surveyor), json={"geometry": corrected, "statement": "Corrected and resubmitted"})
        assert resubmitted.status_code == 200 and resubmitted.json()["verification"]["status"] == "in_review"
        assert client.post(f"/api/verification/{pid_rej}/certify", headers=headers(surveyor), json={}).status_code == 200
        print("PASS rejected -> certify denied until corrected geometry is resubmitted")

        # D: role authorization matches endpoint policy.
        pid_role = "EXT-9878"
        extraction_store.save(ExtractionRecord(
            extraction_id=pid_role, source_filename="role-test.png", geometry=ai,
            image_width=100, image_height=100, image_format="PNG", confidence_heuristic=70,
            pixel_polygon=[[0, 0], [100, 0], [100, 100], [0, 100]],
            inference_mode="test", notes="role test", dataset_id="DS-CERT-TEST"
        ))
        denied_accept = client.post(f"/api/verification/{pid_role}/accept-preliminary", headers=headers(surveyor), json={})
        assert denied_accept.status_code == 403, denied_accept.text
        accepted = client.post(f"/api/verification/{pid_role}/accept-preliminary", headers=headers(admin), json={})
        assert accepted.status_code == 200 and accepted.json()["verification"]["status"] == "verified"
        denied_certify = client.post(f"/api/verification/{pid_role}/certify", headers=headers(gis), json={})
        assert denied_certify.status_code == 403, denied_certify.text
        print("PASS role authorization for accept-preliminary and certify")

        # E: export uses the certified geometry and status for the EXT feature.
        export = client.get("/api/export/geojson", headers=headers(surveyor))
        assert export.status_code == 200, export.text
        feature = next(f for f in export.json()["features"] if f["properties"]["parcel_id"] == pid)
        assert feature["properties"]["verification_status"] == "verified", feature["properties"]
        assert Polygon(feature["geometry"]["coordinates"][0]).equals(_geometry([(1, 1), (12, 1), (12, 9), (1, 9), (1, 1)])), feature["geometry"]
        print("PASS export contains certified geometry and verified status")

        # F: unauthorized user cannot submit or certify; no bearer token gets 401.
        no_auth = client.post(f"/api/verification/{pid}/certify", json={})
        assert no_auth.status_code == 401, no_auth.text
        print("PASS unauthenticated certification rejected")

    print("CERTIFICATION WORKFLOW REGRESSION: PASS (isolated temporary SQLite storage)")


if __name__ == "__main__":
    run_tests()
