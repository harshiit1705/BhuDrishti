"""Import existing BhuDrishti SQLite data into managed PostgreSQL without deleting it.

Usage:
  DATABASE_URL='postgresql://...' python backend/migrate_sqlite_to_postgres.py \
      --sqlite backend/data/bhudrishti.db

The script inserts missing rows only (ON CONFLICT DO NOTHING), preserves the
source SQLite database and upload files, and stores dataset bytes in PostgreSQL.
It prints counts and conflict candidates, never the database URL.
"""
from __future__ import annotations
import argparse
import hashlib
import os
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--sqlite", default=str(Path(__file__).resolve().parent / "data" / "bhudrishti.db"))
    parser.add_argument("--uploads", default=None, help="directory containing legacy dataset upload files")
    args=parser.parse_args()
    dsn=(os.environ.get("DATABASE_URL") or os.environ.get("BHUDRISHTI_DATABASE_URL") or "").strip()
    if not dsn: raise SystemExit("Set DATABASE_URL to the managed PostgreSQL connection string first.")
    try:
        import psycopg
        from psycopg.rows import dict_row
    except ImportError as exc:
        raise SystemExit("Install backend/requirements.txt (psycopg[binary]) before running migration.") from exc
    source=Path(args.sqlite).expanduser().resolve()
    if not source.is_file(): raise SystemExit(f"SQLite source file not found: {source}")
    uploads=Path(args.uploads).expanduser().resolve() if args.uploads else source.parent / "uploads"
    # Create/upgrade destination schema through the same serialized migration
    # path used by deployment, before importing any user data.
    from backend.app.database import initialize_schema
    initialize_schema()
    src=sqlite3.connect(source); src.row_factory=sqlite3.Row
    dst=psycopg.connect(dsn, row_factory=dict_row, connect_timeout=10)
    inserted={}; conflicts={}
    try:
        with dst.transaction():
            for table in ("users","extractions","verifications","datasets"):
                try:
                    cols=[r["name"] for r in src.execute(f"PRAGMA table_info({table})").fetchall()]
                except sqlite3.Error: cols=[]
                if not cols:
                    inserted[table]=0; conflicts[table]=0; continue
                rows=src.execute(f"SELECT * FROM {table}").fetchall()
                n=0; conflict=0
                for row in rows:
                    data=dict(row)
                    if table == "users" and not data.get("user_id"):
                        if data.get("id") is not None:
                            data["user_id"] = str(data["id"])
                        else:
                            email = str(data.get("email") or "").strip().lower()
                            if email:
                                data["user_id"] = hashlib.sha256(("legacy:" + email).encode("utf-8")).hexdigest()[:16]
                            else:
                                raise RuntimeError("Cannot safely import a legacy user row without user_id/id/email; source data was not modified.")
                    if table=="datasets":
                        if "content" not in data or data.get("content") is None:
                            legacy=uploads / str(data.get("dataset_id", ""))
                            data["content"]=legacy.read_bytes() if legacy.is_file() else None
                        cols_insert=[c for c in ("dataset_id","filename","file_type","size_bytes","declared_crs","status","created_at","content") if c in data]
                    elif table=="users":
                        cols_insert=[c for c in ("user_id","email","name","employee_id","department","role","status","password_hash","password_salt","created_at","last_login_at") if c in data]
                    elif table=="extractions":
                        cols_insert=[c for c in ("extraction_id","source_filename","geometry_wkt","image_width","image_height","image_format","confidence_heuristic","pixel_polygon_json","inference_mode","notes","parcel_candidates_json","roof_footprints_json","created_at","status","is_demo_data","dataset_id") if c in data]
                    else:
                        cols_insert=[c for c in ("parcel_id","status","ai_geometry_wkt","verified_geometry_wkt","surveyor_name","surveyor_license","statement","audit_json") if c in data]
                    if not cols_insert: continue
                    placeholders=", ".join(["%s"]*len(cols_insert))
                    colsql=", ".join(cols_insert)
                    cur=dst.execute(f"INSERT INTO {table} ({colsql}) VALUES ({placeholders}) ON CONFLICT DO NOTHING",tuple(data.get(c) for c in cols_insert))
                    if cur.rowcount: n+=1
                    else: conflict+=1
                inserted[table]=n; conflicts[table]=conflict
            # Schema migrations are recorded by initialize_schema(); only sync
            # the sequence after importing existing extraction IDs.
            max_row=dst.execute("SELECT COALESCE(MAX(CAST(substring(extraction_id from 5) AS BIGINT)),0) AS max_id FROM extractions WHERE extraction_id ~ '^EXT-[0-9]+$'").fetchone()
            max_id=int(max_row["max_id"] or 0)
            seq=dst.execute("SELECT last_value,is_called FROM extraction_id_seq").fetchone()
            if max_id and (int(seq["last_value"]) < max_id or (not seq["is_called"] and max_id >= int(seq["last_value"]))):
                dst.execute("SELECT setval('extraction_id_seq',%s,true)",(max_id,))
        # A real SELECT confirms successful destination connection and transaction commit.
        with dst.cursor() as cur:
            cur.execute("SELECT 1 AS connection_ok")
            assert cur.fetchone()["connection_ok"] == 1
    finally:
        src.close(); dst.close()
    print("SQLite import completed. Source database and uploads were not modified.")
    for table in ("users","datasets","extractions","verifications"):
        print(f"{table}: inserted={inserted.get(table,0)} existing-key-skipped={conflicts.get(table,0)}")
    print("Review skipped rows before cutover; this procedure never overwrites destination records.")

if __name__=="__main__": main()
