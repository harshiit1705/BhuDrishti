"""Apply BhuDrishti's additive PostgreSQL schema migrations.

Run once before deploying a new schema version:
  DATABASE_URL='postgresql://...' python backend/migrate_postgres_schema.py

The migration acquires a transaction-scoped PostgreSQL advisory lock, preserves
existing rows, and aborts on ambiguous duplicate user identifiers/emails.
"""
from __future__ import annotations
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


def main() -> int:
    if not (os.environ.get("DATABASE_URL") or os.environ.get("BHUDRISHTI_DATABASE_URL")):
        print("ERROR: Set DATABASE_URL to your managed PostgreSQL/Supabase connection string.", file=sys.stderr)
        return 2
    try:
        from backend.app.database import initialize_schema, check_database
        initialize_schema()
        status = check_database()
    except Exception as exc:
        print(f"ERROR: PostgreSQL schema migration failed ({type(exc).__name__}). Existing data was not intentionally deleted.", file=sys.stderr)
        print("Inspect your database schema and migration logs; connection strings and SQL details are intentionally omitted.", file=sys.stderr)
        return 1
    if not status["connected"] or not status["schema_ready"] or status["adapter"] != "postgresql":
        print("ERROR: Database connection or required schema verification failed.", file=sys.stderr)
        return 1
    print("POSTGRES_SCHEMA_MIGRATION: PASS (connection verified; required schema versions present)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
