"""Small DB-API compatibility layer for SQLite (local) and psycopg 3 (managed PG)."""
from __future__ import annotations
import re
import sqlite3
from .persistence import DATABASE_URL, DB_PATH

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
            raise RuntimeError("PostgreSQL is configured but psycopg is not installed; install backend/requirements.txt") from exc
        raw = psycopg.connect(DATABASE_URL, connect_timeout=int(__import__('os').environ.get("BHUDRISHTI_DB_CONNECT_TIMEOUT", "8")), row_factory=dict_row, prepare_threshold=None)
        return ConnectionAdapter(raw, True)
    raw = sqlite3.connect(sqlite_path or DB_PATH, timeout=15)
    raw.row_factory = sqlite3.Row
    return ConnectionAdapter(raw, False)


def is_postgres() -> bool:
    return bool(DATABASE_URL)


def check_database() -> dict:
    """Perform a real connection and SELECT 1; never infer connected from config alone."""
    try:
        with connect_db() as db:
            row = db.execute("SELECT 1 AS connection_ok").fetchone()
        return {"configured": bool(DATABASE_URL) or not __import__('os').environ.get("VERCEL"), "connected": bool(row and (row.get("connection_ok") == 1 if isinstance(row, dict) else row[0] == 1)), "adapter": "postgresql" if DATABASE_URL else "sqlite_local", "error": None}
    except Exception as exc:
        # Avoid returning DSNs, passwords or arbitrary driver exception strings.
        return {"configured": bool(DATABASE_URL) or not __import__('os').environ.get("VERCEL"), "connected": False, "adapter": "postgresql" if DATABASE_URL else "sqlite_local", "error": type(exc).__name__}
