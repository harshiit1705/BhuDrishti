"""Create the first real production administrator without using demo credentials.

Run from the repository root with DATABASE_URL set. Prompts do not echo passwords.
The command refuses to overwrite an account or create a second active non-demo admin.
"""
from __future__ import annotations
import base64
import getpass
import hashlib
import os
import secrets
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

DEMO_EMAILS = {
    "admin@bhudrishti.gov.in", "project@bhudrishti.gov.in", "gis@bhudrishti.gov.in",
    "surveyor@bhudrishti.gov.in", "revenue@bhudrishti.gov.in",
}


def hash_password(password: str) -> tuple[str, str]:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 210_000)
    return base64.urlsafe_b64encode(digest).decode(), base64.urlsafe_b64encode(salt).decode()


def main() -> int:
    if not (os.environ.get("DATABASE_URL") or os.environ.get("BHUDRISHTI_DATABASE_URL")):
        print("ERROR: Set DATABASE_URL to the intended managed PostgreSQL database.", file=sys.stderr)
        return 2
    email = input("Administrator email: ").strip().lower()
    if not email or "@" not in email or email in DEMO_EMAILS:
        print("ERROR: Use a valid, non-demo administrator email.", file=sys.stderr)
        return 2
    name = input("Administrator full name: ").strip()
    employee_id = input("Employee ID: ").strip()
    department = input("Department: ").strip()
    password = getpass.getpass("New password (minimum 12 characters): ")
    confirmation = getpass.getpass("Confirm password: ")
    if len(password) < 12 or password != confirmation:
        print("ERROR: Passwords must match and contain at least 12 characters.", file=sys.stderr)
        return 2
    from backend.app.database import initialize_schema, connect_db, lock_schema_initialization, is_postgres
    if not is_postgres():
        print("ERROR: This command only supports configured PostgreSQL.", file=sys.stderr)
        return 2
    try:
        initialize_schema()
        password_hash, salt = hash_password(password)
        with connect_db() as db:
            lock_schema_initialization(db)
            admins = db.execute("SELECT COUNT(*) AS n FROM users WHERE role='ADMIN' AND status='ACTIVE' AND lower(email)<>?",
                                ("admin@bhudrishti.gov.in",)).fetchone()["n"]
            # Existing demo admin row is deliberately excluded by email.
            if int(admins) > 0:
                print("ERROR: An active non-demo administrator already exists; no changes made.", file=sys.stderr)
                return 3
            existing = db.execute("SELECT 1 FROM users WHERE lower(email)=lower(?)", (email,)).fetchone()
            if existing:
                print("ERROR: This email already exists; no account was overwritten.", file=sys.stderr)
                return 3
            # Use BhuDrishti's own auth contract. The migration makes any legacy
            # workspace_id optional without deleting workspace records or user rows.
            db.execute(
                """INSERT INTO users(user_id,email,name,employee_id,department,role,status,password_hash,password_salt,created_at)
                   VALUES(?,?,?,?,?,'ADMIN','ACTIVE',?,?,?)""",
                (secrets.token_hex(16), email, name, employee_id, department,
                 password_hash, salt, time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())),
            )

        print("ADMIN_BOOTSTRAP: PASS (one administrator created; password was not printed)")
        return 0
    except Exception as exc:
        print(f"ERROR: Administrator bootstrap failed ({type(exc).__name__}); no credentials were printed.", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
