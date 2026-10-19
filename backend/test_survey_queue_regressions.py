"""Survey queue regressions, including legacy SQLite schema migration.

Uses only temporary database files and never touches backend/data/bhudrishti.db.
Run from repository root with: PYTHONPATH=. python backend/test_survey_queue_regressions.py
"""
from __future__ import annotations
import json
import os
import sqlite3
import tempfile
from pathlib import Path

# Isolate the import-time local SQLite initialization from the bundled project DB.
_BOOTSTRAP_TEMP = tempfile.TemporaryDirectory(prefix="bhudrishti-queue-bootstrap-")
os.environ.pop("VERCEL", None)
os.environ.pop("DATABASE_URL", None)
os.environ.pop("BHUDRISHTI_DATABASE_URL", None)
os.environ["BHUDRISHTI_DB_PATH"] = str(Path(_BOOTSTRAP_TEMP.name) / "bootstrap.sqlite3")

from shapely.geometry import Polygon

from backend.app import main, extraction_store as extraction_module, verification_store as verification_module
from backend.app import database as database_module, persistence as persistence_module, auth as auth_module
from backend.app.extraction_store import ExtractionRecord, PersistentExtractionRepository
from backend.app.verification_store import PersistentVerificationRepository


def make_record(repo, extraction_id="EXT-TEST-001"):
    poly = Polygon([(10, 10), (40, 10), (40, 40), (10, 40)])
    rec = ExtractionRecord(
        extraction_id=extraction_id, source_filename="test.png", geometry=poly,
        image_width=64, image_height=64, image_format="PNG", confidence_heuristic=82.0,
        pixel_polygon=[[10, 10], [40, 10], [40, 40], [10, 40]],
        inference_mode="test_fixture", notes="isolated queue regression fixture",
        dataset_id="DS-TEST-001",
    )
    return repo.save(rec)


def main_test():
    original = (extraction_module.DB_PATH, verification_module.DB_PATH, main.DB_PATH,
                database_module.DB_PATH, persistence_module.DB_PATH, auth_module.DB_PATH,
                main.extraction_store, main.store)
    try:
        with tempfile.TemporaryDirectory(prefix="bhudrishti-queue-test-") as td:
            db_path = Path(td) / "legacy.db"
            # Reproduce the concrete stale-schema condition: existing extraction
            # table from an older release has no dataset_id column.
            with sqlite3.connect(db_path) as db:
                db.execute("""CREATE TABLE extractions (
                    extraction_id TEXT PRIMARY KEY, source_filename TEXT NOT NULL,
                    geometry_wkt TEXT NOT NULL, image_width INTEGER, image_height INTEGER,
                    image_format TEXT, confidence_heuristic REAL, pixel_polygon_json TEXT,
                    inference_mode TEXT, notes TEXT, parcel_candidates_json TEXT,
                    roof_footprints_json TEXT, created_at TEXT, status TEXT, is_demo_data INTEGER
                )""")
                db.execute("""INSERT INTO extractions VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", (
                    "EXT-LEGACY-001", "legacy.png", "POLYGON ((10 10, 40 10, 40 40, 10 40, 10 10))",
                    64, 64, "PNG", 80.0, json.dumps([[10,10],[40,10],[40,40],[10,40]]),
                    "test", "legacy", "[]", "[]", "2026-01-01T00:00:00+00:00", "ai_preliminary", 0
                ))

            extraction_module.DB_PATH = db_path
            verification_module.DB_PATH = db_path
            main.DB_PATH = db_path
            database_module.DB_PATH = db_path
            persistence_module.DB_PATH = db_path
            auth_module.DB_PATH = db_path
            database_module.initialize_schema()
            ext_repo = PersistentExtractionRepository()
            ver_repo = PersistentVerificationRepository()
            # Migration preserves the existing record and makes the new field readable.
            legacy = ext_repo.get("EXT-LEGACY-001")
            assert legacy is not None and legacy.dataset_id is None
            with sqlite3.connect(db_path) as db:
                cols = {r[1] for r in db.execute("PRAGMA table_info(extractions)")}
                assert "dataset_id" in cols
                assert db.execute("SELECT COUNT(*) FROM extractions WHERE extraction_id='EXT-LEGACY-001'").fetchone()[0] == 1

            # Empty extraction table returns only the legitimate seeded queue.
            main.extraction_store = ext_repo
            main.store = ver_repo
            with sqlite3.connect(db_path) as db:
                db.execute("DELETE FROM extractions")
            empty = main._build_survey_queue()
            assert empty["count"] > 0 and empty["contains_seeded_demo_data"] is True
            assert empty["contains_ai_extractions"] is False

            # Valid extraction is included, not lost or replaced with a fake row.
            make_record(ext_repo, "EXT-VALID-001")
            valid = main._build_survey_queue()
            row = next(x for x in valid["queue"] if x.get("parcel_id") == "EXT-VALID-001")
            assert row["is_extraction"] is True and row["is_demo_data"] is False

            # Verified extraction uses its certified geometry/status consistently.
            rec = ext_repo.get("EXT-VALID-001")
            ver_repo.get_or_create(rec.extraction_id, rec.geometry)
            ver_repo.submit_correction(rec.extraction_id, rec.geometry,
                {"type":"Polygon","coordinates":[[[11,11],[41,11],[41,41],[11,41],[11,11]]]},
                "Queue Tester", "TEST-1", "Verified queue fixture")
            ver_repo.certify(rec.extraction_id, "Queue Tester")
            verified = main._build_survey_queue()
            vrow = next(x for x in verified["queue"] if x.get("parcel_id") == "EXT-VALID-001")
            assert vrow["verification_status"] == "verified"
            assert vrow["geometry_source"] == "surveyor_verified"

            # Truly missing extraction is not fabricated by repository lookup.
            assert ext_repo.get("EXT-MISSING-999") is None

            # Repository failure must remain a visible HTTP 500 with a diagnostic
            # correlation ID, never an empty queue/HTTP 200.
            class BrokenRepo:
                def all(self):
                    raise sqlite3.OperationalError("simulated repository read failure")
            class FakeURL:
                path = "/api/survey-queue"
            class FakeRequest:
                method = "GET"
                url = FakeURL()
            main.extraction_store = BrokenRepo()
            try:
                main.get_survey_queue(FakeRequest())
                raise AssertionError("expected HTTP 500 for repository failure")
            except Exception as exc:
                from fastapi import HTTPException
                assert isinstance(exc, HTTPException) and exc.status_code == 500
                assert exc.detail["diagnostic_id"]
            print("SURVEY QUEUE REGRESSIONS: PASS (legacy schema migration, existing record preservation, empty/valid/verified queue, missing ID, diagnostic 500)")
    finally:
        (extraction_module.DB_PATH, verification_module.DB_PATH, main.DB_PATH,
         database_module.DB_PATH, persistence_module.DB_PATH, auth_module.DB_PATH,
         main.extraction_store, main.store) = original


if __name__ == "__main__":
    main_test()
