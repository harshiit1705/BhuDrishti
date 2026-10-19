"""Transactional HITL verification state machine on SQLite or managed PostgreSQL."""
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional
import json
from shapely.geometry import Polygon, mapping
from shapely import wkt
from .geometry_engine import validate_surveyor_geometry
from .database import connect_db, is_postgres
from .persistence import DB_PATH


def _conn(): return connect_db()

@dataclass
class AuditEntry:
    timestamp: str
    actor: str
    action: str
    detail: str

@dataclass
class VerificationRecord:
    parcel_id: str
    status: str = "unverified"
    ai_geometry: Optional[Polygon] = None
    verified_geometry: Optional[Polygon] = None
    surveyor_name: Optional[str] = None
    surveyor_license: Optional[str] = None
    statement: Optional[str] = None
    audit_trail: list = field(default_factory=list)
    def log(self, actor, action, detail=""):
        self.audit_trail.append(AuditEntry(datetime.now(timezone.utc).isoformat(), actor, action, detail))
    def to_dict(self):
        return {"parcel_id":self.parcel_id,"status":self.status,"surveyor_name":self.surveyor_name,
                "surveyor_license":self.surveyor_license,"statement":self.statement,
                "ai_geometry":mapping(self.ai_geometry) if self.ai_geometry else None,
                "verified_geometry":mapping(self.verified_geometry) if self.verified_geometry else None,
                "audit_trail":[a.__dict__ if hasattr(a,'__dict__') else a for a in self.audit_trail]}

class InvalidTransitionError(Exception):
    def __init__(self,current_status,action):
        self.current_status=current_status; self.action=action
        super().__init__(f"Cannot {action} while status is '{current_status}'")

ALLOWED_SUBMIT_FROM={"unverified","in_review","rejected"}
ALLOWED_CERTIFY_FROM={"in_review"}
ALLOWED_REJECT_FROM={"in_review"}
ALLOWED_ACCEPT_PRELIMINARY_FROM={"unverified"}

class PersistentVerificationRepository:
    def __init__(self):
        with _conn() as c:
            c.execute("""CREATE TABLE IF NOT EXISTS verifications (
              parcel_id TEXT PRIMARY KEY,status TEXT,ai_geometry_wkt TEXT,verified_geometry_wkt TEXT,
              surveyor_name TEXT,surveyor_license TEXT,statement TEXT,audit_json TEXT)""")
            c.execute("""CREATE TABLE IF NOT EXISTS schema_migrations (
              component TEXT NOT NULL, version INTEGER NOT NULL,
              applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
              PRIMARY KEY(component, version))""")
            c.execute("INSERT INTO schema_migrations(component, version) VALUES ('verifications', 2) ON CONFLICT(component, version) DO NOTHING")

    def _row(self,row):
        if not row: return None
        audits=[AuditEntry(**a) for a in json.loads(row["audit_json"] or "[]")]
        return VerificationRecord(row["parcel_id"],row["status"],wkt.loads(row["ai_geometry_wkt"]) if row["ai_geometry_wkt"] else None,
          wkt.loads(row["verified_geometry_wkt"]) if row["verified_geometry_wkt"] else None,row["surveyor_name"],row["surveyor_license"],row["statement"],audits)

    def _get(self, conn, pid, lock=False):
        query = "SELECT * FROM verifications WHERE parcel_id=?" + (" FOR UPDATE" if lock and is_postgres() else "")
        return self._row(conn.execute(query,(pid,)).fetchone())

    def _insert_if_missing(self, rec, conn):
        conn.execute("""INSERT INTO verifications (parcel_id,status,ai_geometry_wkt,verified_geometry_wkt,surveyor_name,surveyor_license,statement,audit_json)
            VALUES (?,?,?,?,?,?,?,?) ON CONFLICT(parcel_id) DO NOTHING""",
            (rec.parcel_id,rec.status,rec.ai_geometry.wkt if rec.ai_geometry else None,
             rec.verified_geometry.wkt if rec.verified_geometry else None,rec.surveyor_name,
             rec.surveyor_license,rec.statement,json.dumps([a.__dict__ for a in rec.audit_trail])))

    def _save(self, rec, conn):
        conn.execute("""INSERT INTO verifications (parcel_id,status,ai_geometry_wkt,verified_geometry_wkt,surveyor_name,surveyor_license,statement,audit_json)
            VALUES (?,?,?,?,?,?,?,?) ON CONFLICT(parcel_id) DO UPDATE SET status=excluded.status,
            ai_geometry_wkt=excluded.ai_geometry_wkt, verified_geometry_wkt=excluded.verified_geometry_wkt,
            surveyor_name=excluded.surveyor_name, surveyor_license=excluded.surveyor_license,
            statement=excluded.statement, audit_json=excluded.audit_json""",
            (rec.parcel_id,rec.status,rec.ai_geometry.wkt if rec.ai_geometry else None,
             rec.verified_geometry.wkt if rec.verified_geometry else None,rec.surveyor_name,
             rec.surveyor_license,rec.statement,json.dumps([a.__dict__ for a in rec.audit_trail])))
        if rec.parcel_id.startswith("EXT-"):
            conn.execute("UPDATE extractions SET status=? WHERE extraction_id=?", (rec.status, rec.parcel_id))
        return rec

    def get(self,pid):
        with _conn() as c: return self._get(c,pid)

    def get_or_create(self,pid,ai_geometry):
        with _conn() as c:
            rec=self._get(c,pid,lock=True)
            if rec: return rec
            initial=VerificationRecord(pid,ai_geometry=ai_geometry)
            initial.log("system","created","AI preliminary geometry ingested")
            self._insert_if_missing(initial,c)
            return self._get(c,pid,lock=True)

    def submit_correction(self,pid,ai_geometry,geojson_geometry,surveyor_name,surveyor_license,statement):
        validated=validate_surveyor_geometry(geojson_geometry)
        with _conn() as c:
            rec=self._get(c,pid,lock=True)
            if rec is None:
                initial=VerificationRecord(pid,ai_geometry=ai_geometry)
                initial.log("system","created","AI preliminary geometry ingested")
                self._insert_if_missing(initial,c)
                rec=self._get(c,pid,lock=True)
            if rec.status not in ALLOWED_SUBMIT_FROM: raise InvalidTransitionError(rec.status,"submit")
            rec.verified_geometry=validated; rec.status="in_review"; rec.surveyor_name=surveyor_name
            rec.surveyor_license=surveyor_license; rec.statement=statement
            rec.log(surveyor_name,"submitted_correction",statement or "")
            return self._save(rec,c)

    def certify(self,pid,surveyor_name):
        with _conn() as c:
            rec=self._get(c,pid,lock=True)
            if not rec: raise KeyError(pid)
            if rec.status == "verified": return rec
            if rec.status not in ALLOWED_CERTIFY_FROM: raise InvalidTransitionError(rec.status,"certify")
            if rec.verified_geometry is None: rec.verified_geometry=rec.ai_geometry
            rec.status="verified"; rec.log(surveyor_name,"certified","Boundary certified in prototype workflow")
            return self._save(rec,c)

    def reject(self,pid,surveyor_name,reason):
        with _conn() as c:
            rec=self._get(c,pid,lock=True)
            if not rec: raise KeyError(pid)
            if rec.status not in ALLOWED_REJECT_FROM: raise InvalidTransitionError(rec.status,"reject")
            rec.status="rejected"; rec.log(surveyor_name,"rejected_ai_output",reason)
            return self._save(rec,c)

    def accept_preliminary(self,pid,ai_geometry,surveyor_name):
        with _conn() as c:
            rec=self._get(c,pid,lock=True)
            if rec is None:
                initial=VerificationRecord(pid,ai_geometry=ai_geometry)
                initial.log("system","created","AI preliminary geometry ingested")
                self._insert_if_missing(initial,c)
                rec=self._get(c,pid,lock=True)
            if rec.status not in ALLOWED_ACCEPT_PRELIMINARY_FROM: raise InvalidTransitionError(rec.status,"accept-preliminary")
            rec.verified_geometry=ai_geometry; rec.status="verified"
            rec.log(surveyor_name,"accepted_preliminary","AI geometry accepted without edits")
            return self._save(rec,c)

    def all(self):
        with _conn() as c: return [self._row(r) for r in c.execute("SELECT * FROM verifications").fetchall()]

VerificationStore=PersistentVerificationRepository
store=PersistentVerificationRepository()
