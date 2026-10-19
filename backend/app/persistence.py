"""Database configuration for local SQLite and managed PostgreSQL deployments.

Vercel is deliberately fail-closed: DATABASE_URL (or BHUDRISHTI_DATABASE_URL)
must point at a managed PostgreSQL/Supabase database. There is no ephemeral
SQLite production fallback.
"""
from __future__ import annotations
import os
from pathlib import Path

IS_VERCEL = bool(os.environ.get("VERCEL"))
DATABASE_URL = (os.environ.get("DATABASE_URL") or os.environ.get("BHUDRISHTI_DATABASE_URL") or "").strip()
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = "postgresql://" + DATABASE_URL[len("postgres://"):]

if IS_VERCEL and not DATABASE_URL:
    raise RuntimeError(
        "BhuDrishti requires managed PostgreSQL on Vercel. Set DATABASE_URL "
        "(recommended: Supabase Session pooler connection string) before deployment. "
        "Ephemeral SQLite is not supported in production."
    )
if DATABASE_URL and not DATABASE_URL.startswith(("postgresql://", "postgresql+psycopg://")):
    raise RuntimeError("DATABASE_URL must be a PostgreSQL connection URL; SQLite is not a production adapter.")
if DATABASE_URL.startswith("postgresql+psycopg://"):
    DATABASE_URL = "postgresql://" + DATABASE_URL[len("postgresql+psycopg://"):]

DB_PATH = Path(os.environ.get("BHUDRISHTI_DB_PATH", Path(__file__).resolve().parent.parent / "data" / "bhudrishti.db")).expanduser().resolve()
DB_PATH.parent.mkdir(parents=True, exist_ok=True)
UPLOAD_DIR = DB_PATH.parent / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
PERSISTENCE_MODE = "postgresql" if DATABASE_URL else "sqlite_local"
PERSISTENCE_LABEL = "Managed PostgreSQL/Supabase" if DATABASE_URL else f"Local SQLite file ({DB_PATH})"


def database_configured() -> bool:
    return bool(DATABASE_URL) or not IS_VERCEL
