"""Shared DB-API adapter and serialized, additive schema migrations.

Production migrations are run explicitly with ``python backend/migrate_postgres_schema.py``.
The FastAPI module never performs PostgreSQL DDL at import time. Local SQLite remains
self-initializing for developer convenience.
"""
from __future__ import annotations

import os
import re
import sqlite3
import uuid
from .persistence import DATABASE_URL, DB_PATH, IS_VERCEL

_QMARK = re.compile(r"\?")


class ConnectionAdapter:
    def __init__(self, raw, postgres: bool):
        self.raw = raw
        self.postgres = postgres

    def execute(self, sql, params=()):
        if self.postgres:
            sql = _QMARK.sub("%s", sql)
        return self.raw.execute(sql, params)

    def commit(self): return self.raw.commit()
    def rollback(self): return self.raw.rollback()
    def close(self): return self.raw.close()

    def __enter__(self): return self
    def __exit__(self, exc_type, exc, tb):
        try:
            if exc_type is None: self.commit()
            else: self.rollback()
        finally:
            self.close()
        return False


def connect_db(sqlite_path=None) -> ConnectionAdapter:
    if DATABASE_URL:
        try:
            import psycopg
            from psycopg.rows import dict_row
        except ImportError as exc:
            raise RuntimeError("PostgreSQL is configured but psycopg is not installed; install requirements.txt") from exc
        raw = psycopg.connect(
            DATABASE_URL,
            connect_timeout=int(os.environ.get("BHUDRISHTI_DB_CONNECT_TIMEOUT", "8")),
            row_factory=dict_row,
            prepare_threshold=None,
        )
        return ConnectionAdapter(raw, True)
    if IS_VERCEL:
        raise RuntimeError("Managed PostgreSQL must be configured on Vercel; SQLite fallback is disabled.")
    raw = sqlite3.connect(sqlite_path or DB_PATH, timeout=15)
    raw.row_factory = sqlite3.Row
    return ConnectionAdapter(raw, False)


def is_postgres() -> bool:
    return bool(DATABASE_URL)


def lock_schema_initialization(db) -> None:
    """Serialize PostgreSQL schema migration transactions across serverless workers."""
    if is_postgres():
        db.execute("SELECT pg_advisory_xact_lock(1842052026)")


def _columns(db, table: str, postgres: bool) -> set[str]:
    if postgres:
        return {r["column_name"] for r in db.execute(
            "SELECT column_name FROM information_schema.columns WHERE table_schema=current_schema() AND table_name=?",
            (table,),
        ).fetchall()}
    return {r[1] for r in db.execute(f"PRAGMA table_info({table})").fetchall()}


def _add_missing_columns(db, table: str, definitions: dict[str, str], postgres: bool) -> None:
    present = _columns(db, table, postgres)
    for name, definition in definitions.items():
        if name not in present:
            db.execute(f"ALTER TABLE {table} ADD COLUMN {name} {definition}")


def initialize_schema() -> None:
    """Apply additive, repeatable schema migrations under one transaction/lock.

    Existing rows are never dropped or rewritten except for filling absent user IDs.
    If legacy user emails conflict with the required case-insensitive unique index,
    migration fails rather than deleting or silently merging accounts.
    """
    pg = is_postgres()
    with connect_db() as db:
        if not pg:
            # Acquire SQLite's writer lock before schema introspection so two
            # local workers cannot both decide to add the same legacy column.
            db.execute("BEGIN IMMEDIATE")
        lock_schema_initialization(db)
        db.execute("""CREATE TABLE IF NOT EXISTS schema_migrations (
            component TEXT NOT NULL, version INTEGER NOT NULL,
            applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY(component, version))""")

        db.execute("""CREATE TABLE IF NOT EXISTS users (
            user_id TEXT PRIMARY KEY, email TEXT UNIQUE NOT NULL, name TEXT NOT NULL,
            employee_id TEXT, department TEXT, role TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'ACTIVE', password_hash TEXT NOT NULL,
            password_salt TEXT NOT NULL, created_at TEXT NOT NULL, last_login_at TEXT)""")
        original_user_columns = _columns(db, "users", pg)
        _add_missing_columns(db, "users", {
            "user_id": "TEXT", "email": "TEXT", "name": "TEXT", "employee_id": "TEXT",
            "department": "TEXT", "role": "TEXT", "status": "TEXT DEFAULT 'ACTIVE'",
            "password_hash": "TEXT DEFAULT ''", "password_salt": "TEXT DEFAULT ''",
            "created_at": "TEXT DEFAULT ''", "last_login_at": "TEXT",
        }, pg)
        if pg:
            # Older deployments may have an unrelated workspace-based auth schema:
            # workspace_id NOT NULL plus CHECK constraints that only permit
            # lowercase ApexOS roles/statuses. BhuDrishti owns its user model and
            # does not write workspace_id. Preserve legacy columns/rows/FKs, but
            # remove the incompatible NOT NULL and role/status CHECK constraints.
            user_columns = _columns(db, "users", True)
            if "workspace_id" in user_columns:
                db.execute("ALTER TABLE users ALTER COLUMN workspace_id DROP NOT NULL")
            checks = db.execute("""SELECT conname, pg_get_constraintdef(oid) AS definition
                FROM pg_constraint WHERE conrelid = to_regclass('public.users') AND contype = 'c'""").fetchall()
            for check in checks:
                definition = str(check["definition"] or "").lower()
                if "role" in definition or "status" in definition:
                    constraint_name = str(check["conname"]).replace('"', '""')
                    db.execute(f'ALTER TABLE users DROP CONSTRAINT "{constraint_name}"')
        # If an older deployment used `id` as its identifier, preserve it where
        # possible before generating a stable fallback for remaining rows.
        if "id" in original_user_columns:
            db.execute("UPDATE users SET user_id=CAST(id AS TEXT) WHERE (user_id IS NULL OR user_id='') AND id IS NOT NULL")
        users = db.execute("SELECT email, user_id FROM users WHERE user_id IS NULL OR user_id='' ").fetchall()
        for row in users:
            email = str(row["email"] or "").strip().lower()
            stable_id = __import__("hashlib").sha256(("legacy:" + email).encode()).hexdigest()[:16] if email else uuid.uuid4().hex[:16]
            db.execute("UPDATE users SET user_id=? WHERE (user_id IS NULL OR user_id='') AND ((email IS NULL AND ? IS NULL) OR email=?)", (stable_id, row["email"], row["email"]))
        duplicate_emails = db.execute("""SELECT COUNT(*) AS n FROM (
            SELECT lower(email) AS e FROM users WHERE email IS NOT NULL AND trim(email)<>''
            GROUP BY lower(email) HAVING COUNT(*) > 1) d""").fetchone()["n"]
        if duplicate_emails:
            raise RuntimeError("Schema migration blocked: duplicate case-insensitive users.email values exist; reconcile them manually before retrying.")
        duplicate_ids = db.execute("""SELECT COUNT(*) AS n FROM (
            SELECT user_id FROM users WHERE user_id IS NOT NULL GROUP BY user_id HAVING COUNT(*) > 1) d""").fetchone()["n"]
        if duplicate_ids:
            raise RuntimeError("Schema migration blocked: duplicate users.user_id values exist; reconcile them manually before retrying.")
        db.execute("CREATE UNIQUE INDEX IF NOT EXISTS users_user_id_uq ON users(user_id)")
        db.execute("CREATE UNIQUE INDEX IF NOT EXISTS users_email_lower_uq ON users(lower(email))")

        db.execute("""CREATE TABLE IF NOT EXISTS datasets (
            dataset_id TEXT PRIMARY KEY, filename TEXT, file_type TEXT, size_bytes BIGINT,
            declared_crs TEXT, status TEXT, created_at TEXT, content BYTEA)""" if pg else """CREATE TABLE IF NOT EXISTS datasets (
            dataset_id TEXT PRIMARY KEY, filename TEXT, file_type TEXT, size_bytes BIGINT,
            declared_crs TEXT, status TEXT, created_at TEXT, content BLOB)""")
        _add_missing_columns(db, "datasets", {
            "dataset_id": "TEXT", "filename": "TEXT", "file_type": "TEXT", "size_bytes": "BIGINT",
            "declared_crs": "TEXT", "status": "TEXT", "created_at": "TEXT", "content": "BYTEA" if pg else "BLOB",
        }, pg)

        db.execute("""CREATE TABLE IF NOT EXISTS extractions (
            extraction_id TEXT PRIMARY KEY, source_filename TEXT NOT NULL, geometry_wkt TEXT NOT NULL,
            image_width INTEGER, image_height INTEGER, image_format TEXT, confidence_heuristic DOUBLE PRECISION,
            pixel_polygon_json TEXT, inference_mode TEXT, notes TEXT, parcel_candidates_json TEXT,
            roof_footprints_json TEXT, created_at TEXT, status TEXT, is_demo_data INTEGER, dataset_id TEXT)""")
        _add_missing_columns(db, "extractions", {
            "extraction_id": "TEXT", "source_filename": "TEXT", "geometry_wkt": "TEXT", "image_width": "INTEGER",
            "image_height": "INTEGER", "image_format": "TEXT", "confidence_heuristic": "DOUBLE PRECISION" if pg else "REAL",
            "pixel_polygon_json": "TEXT", "inference_mode": "TEXT", "notes": "TEXT", "parcel_candidates_json": "TEXT",
            "roof_footprints_json": "TEXT", "created_at": "TEXT", "status": "TEXT", "is_demo_data": "INTEGER", "dataset_id": "TEXT",
        }, pg)

        db.execute("""CREATE TABLE IF NOT EXISTS verifications (
            parcel_id TEXT PRIMARY KEY, status TEXT, ai_geometry_wkt TEXT, verified_geometry_wkt TEXT,
            surveyor_name TEXT, surveyor_license TEXT, statement TEXT, audit_json TEXT)""")
        _add_missing_columns(db, "verifications", {
            "parcel_id": "TEXT", "status": "TEXT", "ai_geometry_wkt": "TEXT", "verified_geometry_wkt": "TEXT",
            "surveyor_name": "TEXT", "surveyor_license": "TEXT", "statement": "TEXT", "audit_json": "TEXT",
        }, pg)

        for component, version in (("auth_users", 4), ("datasets", 3), ("extractions", 3), ("verifications", 3)):
            db.execute("INSERT INTO schema_migrations(component, version) VALUES (?, ?) ON CONFLICT(component, version) DO NOTHING", (component, version))

        if pg:
            db.execute("CREATE SEQUENCE IF NOT EXISTS extraction_id_seq START WITH 1")
            max_row = db.execute("SELECT COALESCE(MAX(CAST(substring(extraction_id from 5) AS BIGINT)),0) AS max_id FROM extractions WHERE extraction_id ~ '^EXT-[0-9]+$'").fetchone()
            seq = db.execute("SELECT last_value, is_called FROM extraction_id_seq").fetchone()
            max_id = int(max_row["max_id"] or 0)
            current = int(seq["last_value"])
            if max_id > current or (max_id == current and not seq["is_called"] and max_id > 0):
                db.execute("SELECT setval('extraction_id_seq', ?, true)", (max_id,))


def check_database() -> dict:
    """Report actual connectivity and schema readiness without exposing exception text."""
    adapter = "postgresql" if is_postgres() else "sqlite_local"
    configured = bool(DATABASE_URL) or not IS_VERCEL
    connected = False
    schema_ready = False
    error = None
    try:
        with connect_db() as db:
            row = db.execute("SELECT 1 AS connection_ok").fetchone()
            connected = bool(row and (row.get("connection_ok") == 1 if isinstance(row, dict) else row[0] == 1))
            if connected:
                if is_postgres():
                    exists = db.execute("SELECT to_regclass('public.schema_migrations') AS table_name").fetchone()["table_name"]
                else:
                    exists = db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='schema_migrations'").fetchone()
                if exists:
                    versions = {(r["component"], int(r["version"])) for r in db.execute("SELECT component, version FROM schema_migrations").fetchall()}
                    schema_ready = all((name, version) in versions for name, version in (("auth_users", 4), ("datasets", 3), ("extractions", 3), ("verifications", 3)))
                    if schema_ready and is_postgres():
                        required = {r["column_name"] for r in db.execute("""SELECT column_name FROM information_schema.columns
                            WHERE table_schema=current_schema() AND table_name='users'""").fetchall()}
                        schema_ready = {"user_id", "email", "name", "role", "status", "password_hash", "password_salt"}.issubset(required)
                        if schema_ready and "workspace_id" in required:
                            workspace_nullable = db.execute("""SELECT is_nullable FROM information_schema.columns
                                WHERE table_schema=current_schema() AND table_name='users' AND column_name='workspace_id'""").fetchone()
                            schema_ready = bool(workspace_nullable and workspace_nullable["is_nullable"] == "YES")
                        if schema_ready:
                            remaining_checks = db.execute("""SELECT pg_get_constraintdef(oid) AS definition
                                FROM pg_constraint WHERE conrelid = to_regclass('public.users') AND contype = 'c'""").fetchall()
                            schema_ready = not any(
                                "role" in str(item["definition"] or "").lower()
                                or "status" in str(item["definition"] or "").lower()
                                for item in remaining_checks
                            )
    except Exception as exc:
        error = type(exc).__name__
    if connected and not schema_ready and error is None:
        error = "SchemaNotReady"
    return {"configured": configured, "connected": connected, "schema_ready": schema_ready,
            "adapter": adapter, "error": error}
