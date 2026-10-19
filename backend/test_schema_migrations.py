"""Database adapter/schema regression tests; no project or production DB is touched."""
from __future__ import annotations
import os
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run():
    with tempfile.TemporaryDirectory(prefix="bhudrishti-schema-tests-") as td:
        db_path = Path(td) / "legacy.sqlite3"
        with sqlite3.connect(db_path) as db:
            db.execute("CREATE TABLE users (id INTEGER PRIMARY KEY, email TEXT, name TEXT, role TEXT)")
            db.execute("INSERT INTO users(id,email,name,role) VALUES (7,'legacy@example.test','Legacy User','FIELD_SURVEYOR')")
            db.execute("""CREATE TABLE extractions (extraction_id TEXT PRIMARY KEY, source_filename TEXT NOT NULL,
                geometry_wkt TEXT NOT NULL, image_width INTEGER, image_height INTEGER, image_format TEXT,
                confidence_heuristic REAL, pixel_polygon_json TEXT, inference_mode TEXT, notes TEXT,
                parcel_candidates_json TEXT, roof_footprints_json TEXT, created_at TEXT, status TEXT, is_demo_data INTEGER)""")
            db.execute("INSERT INTO extractions(extraction_id,source_filename,geometry_wkt) VALUES ('EXT-LEGACY-77','legacy.png','POLYGON ((0 0, 2 0, 2 2, 0 2, 0 0))')")

        env = os.environ.copy()
        env.pop("VERCEL", None); env.pop("DATABASE_URL", None); env.pop("BHUDRISHTI_DATABASE_URL", None)
        env["BHUDRISHTI_DB_PATH"] = str(db_path)
        env["PYTHONPATH"] = str(ROOT) + os.pathsep + env.get("PYTHONPATH", "")
        script = "from backend.app.database import initialize_schema, check_database; initialize_schema(); initialize_schema(); print(check_database())"
        r = subprocess.run([sys.executable, "-c", script], cwd=ROOT, env=env, text=True, capture_output=True)
        assert r.returncode == 0, r.stdout + r.stderr
        assert "'schema_ready': True" in r.stdout
        with sqlite3.connect(db_path) as db:
            user = db.execute("SELECT user_id,email,name,role FROM users WHERE email='legacy@example.test'").fetchone()
            assert user == ('7','legacy@example.test','Legacy User','FIELD_SURVEYOR'), user
            ext = db.execute("SELECT extraction_id,dataset_id FROM extractions WHERE extraction_id='EXT-LEGACY-77'").fetchone()
            assert ext == ('EXT-LEGACY-77', None), ext
            versions = db.execute("SELECT COUNT(*) FROM schema_migrations WHERE version=3").fetchone()[0]
            assert versions == 4, versions

        # Multiple independent workers concurrently initializing a fresh SQLite DB.
        concurrent_db = Path(td) / "concurrent.sqlite3"
        env["BHUDRISHTI_DB_PATH"] = str(concurrent_db)
        worker = "from backend.app.database import initialize_schema; initialize_schema(); print('INIT_OK')"
        procs = [subprocess.Popen([sys.executable, "-c", worker], cwd=ROOT, env=env, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE) for _ in range(5)]
        outputs = [p.communicate(timeout=30) + (p.returncode,) for p in procs]
        assert all(code == 0 and "INIT_OK" in out for out, err, code in outputs), outputs

        # A reachable database with a missing schema is degraded, not healthy.
        env["BHUDRISHTI_DB_PATH"] = str(Path(td) / "health.sqlite3")
        health_script = "import json; from fastapi.responses import JSONResponse; from backend.app import main; main.check_database=lambda: {'configured':True,'connected':True,'schema_ready':False,'adapter':'sqlite_local','error':'SchemaNotReady'}; r=main.health(); assert isinstance(r,JSONResponse) and r.status_code==503; assert json.loads(r.body)['persistence']['schema_ready'] is False; print('HEALTH_SCHEMA_NOT_READY_PASS')"
        r = subprocess.run([sys.executable, "-c", health_script], cwd=ROOT, env=env, text=True, capture_output=True)
        assert r.returncode == 0 and "HEALTH_SCHEMA_NOT_READY_PASS" in r.stdout, r.stdout + r.stderr

    # SQL adapter placeholder translation without requiring a live PostgreSQL server.
    from backend.app import database as database_module
    from backend.app.database import ConnectionAdapter
    class FakeConnection:
        def execute(self, sql, params):
            self.sql, self.params = sql, params
            return self
    fake = FakeConnection()
    ConnectionAdapter(fake, postgres=True).execute("SELECT ? AS value WHERE ? = ?", (9, 9, 9))
    assert fake.sql == "SELECT %s AS value WHERE %s = %s" and fake.params == (9, 9, 9)
    lock_calls = []
    class LockConnection:
        def execute(self, sql, params=()): lock_calls.append((sql, params))
    original_is_postgres = database_module.is_postgres
    try:
        database_module.is_postgres = lambda: True
        database_module.lock_schema_initialization(LockConnection())
    finally:
        database_module.is_postgres = original_is_postgres
    assert lock_calls == [("SELECT pg_advisory_xact_lock(1842052026)", ())], lock_calls
    print("SCHEMA MIGRATIONS: PASS (legacy user id preservation, extraction migration, idempotency, concurrent SQLite init, health schema-readiness response, PostgreSQL placeholder translation/advisory lock)")


if __name__ == "__main__":
    run()
