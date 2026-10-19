"""Prototype authentication and role-based authorization for BhuDrishti.

This module intentionally uses only Python stdlib primitives so the prototype
can deploy without a third-party JWT/auth package. Passwords are PBKDF2-hashed
and sessions are signed, expiring HMAC tokens. Production deployment should
move the user store to a managed database/identity provider and set
BHUDRISHTI_AUTH_SECRET as a strong environment secret.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import sqlite3
import time
from pathlib import Path

AUTH_SECRET = os.environ.get("BHUDRISHTI_AUTH_SECRET", "bhudrishti-prototype-change-me")
if os.environ.get("VERCEL") and (not os.environ.get("BHUDRISHTI_AUTH_SECRET") or AUTH_SECRET == "bhudrishti-prototype-change-me"):
    raise RuntimeError("BHUDRISHTI_AUTH_SECRET must be configured to a strong random secret on Vercel.")
TOKEN_TTL_SECONDS = 8 * 60 * 60

ROLES = {
    "ADMIN",
    "PROJECT_OFFICER",
    "GIS_OPERATOR",
    "FIELD_SURVEYOR",
    "REVENUE_OFFICER",
}

ROLE_LABELS = {
    "ADMIN": "Administrator",
    "PROJECT_OFFICER": "Project Officer",
    "GIS_OPERATOR": "GIS / AI Operator",
    "FIELD_SURVEYOR": "Field Surveyor",
    "REVENUE_OFFICER": "Revenue / Land Records Officer",
}

DEMO_USERS = [
    ("admin@bhudrishti.gov.in", "Bhu@Admin2026", "BhuDrishti Administrator", "ADMIN", "ADMIN-001"),
    ("project@bhudrishti.gov.in", "Bhu@Project2026", "Project Officer", "PROJECT_OFFICER", "PROJ-001"),
    ("gis@bhudrishti.gov.in", "Bhu@GIS2026", "GIS / AI Operator", "GIS_OPERATOR", "GIS-001"),
    ("surveyor@bhudrishti.gov.in", "Bhu@Survey2026", "Field Surveyor", "FIELD_SURVEYOR", "SURV-001"),
    ("revenue@bhudrishti.gov.in", "Bhu@Revenue2026", "Revenue Officer", "REVENUE_OFFICER", "REV-001"),
]


from .persistence import DB_PATH
from .database import connect_db, is_postgres, lock_schema_initialization

def _db_path() -> Path:
    return DB_PATH

def _connect():
    db = connect_db()
    try:
        lock_schema_initialization(db)
        db.execute(
            """CREATE TABLE IF NOT EXISTS users (
                user_id TEXT PRIMARY KEY, email TEXT UNIQUE NOT NULL, name TEXT NOT NULL,
                employee_id TEXT, department TEXT, role TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'ACTIVE', password_hash TEXT NOT NULL,
                password_salt TEXT NOT NULL, created_at TEXT NOT NULL, last_login_at TEXT
            )"""
        )
        # Earlier deployed versions may already have created `users` with a
        # different column set. CREATE TABLE IF NOT EXISTS does not migrate it.
        # Add expected fields in-place and preserve existing rows/data.
        required = {
            "user_id": "TEXT", "email": "TEXT", "name": "TEXT",
            "employee_id": "TEXT", "department": "TEXT", "role": "TEXT",
            "status": "TEXT DEFAULT 'ACTIVE'", "password_hash": "TEXT DEFAULT ''",
            "password_salt": "TEXT DEFAULT ''", "created_at": "TEXT DEFAULT ''",
            "last_login_at": "TEXT",
        }
        if is_postgres():
            for column, definition in required.items():
                db.execute(f"ALTER TABLE users ADD COLUMN IF NOT EXISTS {column} {definition}")
        else:
            columns = {row[1] for row in db.execute("PRAGMA table_info(users)").fetchall()}
            for column, definition in required.items():
                if column not in columns:
                    db.execute(f"ALTER TABLE users ADD COLUMN {column} {definition}")
        # Backfill stable IDs for pre-existing accounts before any code queries
        # or updates by user_id. Do not overwrite IDs already in use.
        rows = db.execute("SELECT email, user_id FROM users WHERE user_id IS NULL OR user_id='' ").fetchall()
        for row in rows:
            email = row["email"]
            stable_id = hashlib.sha256(("legacy:" + str(email).lower().strip()).encode("utf-8")).hexdigest()[:16]
            db.execute("UPDATE users SET user_id=? WHERE email=? AND (user_id IS NULL OR user_id='')", (stable_id, email))
        db.execute("CREATE TABLE IF NOT EXISTS schema_migrations (component TEXT NOT NULL, version INTEGER NOT NULL, applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, PRIMARY KEY(component, version))")
        db.execute("INSERT INTO schema_migrations(component, version) VALUES ('auth_users', 2) ON CONFLICT(component, version) DO NOTHING")
        db.commit()
        return db
    except Exception:
        db.rollback()
        db.close()
        raise


def _hash_password(password: str, salt: bytes | None = None) -> tuple[str, str]:
    salt = salt or secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 210_000)
    return base64.urlsafe_b64encode(digest).decode(), base64.urlsafe_b64encode(salt).decode()


def _verify_password(password: str, password_hash: str, password_salt: str) -> bool:
    salt = base64.urlsafe_b64decode(password_salt.encode())
    expected = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 210_000)
    actual = base64.urlsafe_b64decode(password_hash.encode())
    return hmac.compare_digest(expected, actual)


def _b64(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode().rstrip("=")


def _unb64(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def _token(payload: dict) -> str:
    header = {"alg": "HS256", "typ": "JWT"}
    h = _b64(json.dumps(header, separators=(",", ":")).encode())
    p = _b64(json.dumps(payload, separators=(",", ":")).encode())
    signature = _b64(hmac.new(AUTH_SECRET.encode(), f"{h}.{p}".encode(), hashlib.sha256).digest())
    return f"{h}.{p}.{signature}"


def _decode_token(token: str) -> dict:
    parts = token.split(".")
    if len(parts) != 3:
        raise ValueError("Invalid session token")
    h, p, sig = parts
    expected = _b64(hmac.new(AUTH_SECRET.encode(), f"{h}.{p}".encode(), hashlib.sha256).digest())
    if not hmac.compare_digest(sig, expected):
        raise ValueError("Invalid session signature")
    payload = json.loads(_unb64(p).decode())
    if int(payload.get("exp", 0)) < int(time.time()):
        raise ValueError("Session expired")
    return payload


def _public_user(row: sqlite3.Row | dict) -> dict:
    data = dict(row)
    return {
        "user_id": data["user_id"],
        "email": data["email"],
        "name": data["name"],
        "employee_id": data.get("employee_id"),
        "department": data.get("department"),
        "role": data["role"],
        "role_label": ROLE_LABELS.get(data["role"], data["role"]),
        "status": data["status"],
        "created_at": data.get("created_at"),
        "last_login_at": data.get("last_login_at"),
    }


def ensure_demo_users() -> None:
    db = _connect()
    try:
        for email, password, name, role, employee_id in DEMO_USERS:
            stable_id = hashlib.sha256(("demo:" + email.lower().strip()).encode("utf-8")).hexdigest()[:16]
            exists = db.execute("SELECT user_id FROM users WHERE email=?", (email,)).fetchone()
            password_hash, salt = _hash_password(password)
            if exists:
                # Repair pre-existing demo rows as well as their schema. This
                # makes seeded credentials usable after a schema migration.
                db.execute(
                    "UPDATE users SET user_id=?, name=?, employee_id=?, department=?, role=?, status='ACTIVE', password_hash=?, password_salt=? WHERE email=?",
                    (stable_id, name, employee_id, "BhuDrishti Demo Department", role, password_hash, salt, email),
                )
                continue
            db.execute(
                "INSERT INTO users(user_id,email,name,employee_id,department,role,status,password_hash,password_salt,created_at) VALUES(?,?,?,?,?,?,?,?,?,?)",
                (stable_id, email, name, employee_id, "BhuDrishti Demo Department", role, "ACTIVE", password_hash, salt, time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())),
            )
        db.commit()
    finally:
        db.close()


def authenticate(email: str, password: str) -> dict:
    ensure_demo_users()
    db = _connect()
    try:
        row = db.execute("SELECT * FROM users WHERE lower(email)=lower(?)", (email.strip(),)).fetchone()
        if not row or row["status"] != "ACTIVE" or not _verify_password(password, row["password_hash"], row["password_salt"]):
            raise ValueError("Invalid email/password or inactive account")
        now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        db.execute("UPDATE users SET last_login_at=? WHERE user_id=?", (now, row["user_id"]))
        db.commit()
        user = _public_user(dict(row))
        user["last_login_at"] = now
        return user
    finally:
        db.close()


def issue_token(user: dict) -> str:
    now = int(time.time())
    return _token({
        "sub": user["user_id"],
        "email": user["email"],
        "name": user["name"],
        "employee_id": user.get("employee_id"),
        "department": user.get("department"),
        "role": user["role"],
        "iat": now,
        "exp": now + TOKEN_TTL_SECONDS,
    })


def user_from_token(token: str) -> dict:
    payload = _decode_token(token)
    db = _connect()
    try:
        row = db.execute("SELECT * FROM users WHERE user_id=?", (payload.get("sub"),)).fetchone()
        if row and row["status"] == "ACTIVE":
            return _public_user(row)

        # Vercel serverless instances can have different temporary SQLite
        # files. Built-in demo identities are therefore reconstructible from
        # the signed token when the local row is missing. Registered users are
        # never reconstructed this way; their account must exist in persistent
        # storage before it can authenticate.
        demo_by_email = {u[0]: u for u in DEMO_USERS}
        demo = demo_by_email.get(str(payload.get("email", "")).strip().lower())
        if demo and payload.get("role") == demo[3]:
            return {
                "user_id": payload.get("sub"),
                "email": demo[0],
                "name": demo[2],
                "employee_id": demo[4],
                "department": "BhuDrishti Demo Department",
                "role": demo[3],
                "role_label": ROLE_LABELS.get(demo[3], demo[3]),
                "status": "ACTIVE",
                "created_at": None,
                "last_login_at": None,
            }
        raise ValueError("Account is inactive")
    finally:
        db.close()


def create_registration(email: str, password: str, name: str, employee_id: str, department: str, role: str) -> dict:
    role = role.upper().strip()
    if role not in ROLES or role == "ADMIN":
        raise ValueError("Requested role is not allowed")
    if len(password) < 10:
        raise ValueError("Password must be at least 10 characters")
    db = _connect()
    try:
        if db.execute("SELECT 1 FROM users WHERE lower(email)=lower(?)", (email.strip(),)).fetchone():
            raise ValueError("An account with this email already exists")
        password_hash, salt = _hash_password(password)
        user_id = secrets.token_hex(8)
        created = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        db.execute(
            "INSERT INTO users(user_id,email,name,employee_id,department,role,status,password_hash,password_salt,created_at) VALUES(?,?,?,?,?,?,?,?,?,?)",
            (user_id, email.strip().lower(), name.strip(), employee_id.strip(), department.strip(), role, "PENDING", password_hash, salt, created),
        )
        db.commit()
        return {"user_id": user_id, "email": email.strip().lower(), "status": "PENDING", "role": role, "role_label": ROLE_LABELS[role]}
    finally:
        db.close()


def list_users() -> list[dict]:
    ensure_demo_users()
    db = _connect()
    try:
        return [_public_user(row) for row in db.execute("SELECT * FROM users ORDER BY created_at DESC").fetchall()]
    finally:
        db.close()


def set_user_status(user_id: str, status: str) -> dict:
    status = status.upper().strip()
    if status not in {"ACTIVE", "SUSPENDED", "PENDING"}:
        raise ValueError("Invalid user status")
    db = _connect()
    try:
        cur = db.execute("UPDATE users SET status=? WHERE user_id=?", (status, user_id))
        if cur.rowcount != 1:
            raise ValueError("User not found")
        db.commit()
        row = db.execute("SELECT * FROM users WHERE user_id=?", (user_id,)).fetchone()
        return _public_user(row)
    finally:
        db.close()
