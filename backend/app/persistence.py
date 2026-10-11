"""Shared persistence configuration for all BhuDrishti backend stores.

Local development uses the bundled project database unless BHUDRISHTI_DB_PATH
is supplied. Vercel serverless instances MUST NOT silently use /tmp: this build
has no PostgreSQL driver/repository adapter, so deployment fails closed unless
an operator explicitly opts into unsafe prototype-only ephemeral storage.
"""
from __future__ import annotations
import os
from pathlib import Path
import warnings

IS_VERCEL = bool(os.environ.get("VERCEL"))
DATABASE_URL = os.environ.get("DATABASE_URL") or os.environ.get("BHUDRISHTI_DATABASE_URL")
ALLOW_EPHEMERAL = os.environ.get("BHUDRISHTI_ALLOW_EPHEMERAL_SQLITE", "").strip().lower() in {"1", "true", "yes"}

if IS_VERCEL and DATABASE_URL:
    raise RuntimeError(
        "BhuDrishti production persistence is not configured: DATABASE_URL is present, "
        "but this build does not include a PostgreSQL repository adapter. Refusing to "
        "silently ignore DATABASE_URL and use per-instance SQLite. Deploy a build with "
        "the managed PostgreSQL adapter before setting DATABASE_URL."
    )
if IS_VERCEL and not ALLOW_EPHEMERAL:
    raise RuntimeError(
        "BhuDrishti cannot start on Vercel with ephemeral SQLite persistence. "
        "Configure a managed PostgreSQL/Supabase database and deploy a PostgreSQL-capable "
        "build. For a temporary demo only, explicitly set BHUDRISHTI_ALLOW_EPHEMERAL_SQLITE=1; "
        "records and uploads may disappear or differ between instances."
    )
if IS_VERCEL and ALLOW_EPHEMERAL:
    warnings.warn("UNSAFE PROTOTYPE MODE: Vercel /tmp SQLite is not shared or durable.", RuntimeWarning)

if os.environ.get("BHUDRISHTI_DB_PATH"):
    DB_PATH = Path(os.environ["BHUDRISHTI_DB_PATH"]).expanduser().resolve()
elif IS_VERCEL:
    DB_PATH = Path("/tmp/bhudrishti") / "bhudrishti.db"
else:
    DB_PATH = Path(__file__).resolve().parent.parent / "data" / "bhudrishti.db"

DB_PATH.parent.mkdir(parents=True, exist_ok=True)
UPLOAD_DIR = DB_PATH.parent / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
