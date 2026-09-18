"""
Human-in-the-loop verification store.

Real state machine + audit trail, held in-memory for the prototype
(swap for a DB table in production -- the interface would not change).
Distinguishes AI-generated preliminary geometry from surveyor-certified
geometry at all times, per project requirement.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional
from shapely.geometry import Polygon, mapping
from .geometry_engine import validate_surveyor_geometry


@dataclass
class AuditEntry:
    timestamp: str
    actor: str
    action: str
    detail: str


@dataclass
class VerificationRecord:
    parcel_id: str
    status: str = "unverified"          # unverified | in_review | verified | rejected
    ai_geometry: Optional[Polygon] = None
    verified_geometry: Optional[Polygon] = None
    surveyor_name: Optional[str] = None
    surveyor_license: Optional[str] = None
    statement: Optional[str] = None
    audit_trail: list = field(default_factory=list)

    def log(self, actor: str, action: str, detail: str = ""):
        self.audit_trail.append(AuditEntry(
            timestamp=datetime.now(timezone.utc).isoformat(),
            actor=actor, action=action, detail=detail,
        ))

    def to_dict(self):
        return {
            "parcel_id": self.parcel_id,
            "status": self.status,
            "surveyor_name": self.surveyor_name,
            "surveyor_license": self.surveyor_license,
            "statement": self.statement,
            "ai_geometry": mapping(self.ai_geometry) if self.ai_geometry else None,
            "verified_geometry": mapping(self.verified_geometry) if self.verified_geometry else None,
            "audit_trail": [a.__dict__ for a in self.audit_trail],
        }


class InvalidTransitionError(Exception):
    """Raised when an action is attempted from a status that doesn't allow it.
    The API layer catches this and returns HTTP 409."""
    def __init__(self, current_status: str, action: str):
        self.current_status = current_status
        self.action = action
        super().__init__(f"Cannot {action} while status is '{current_status}'")


# Legal transitions: unverified/in_review -> in_review (submit), in_review -> verified/rejected,
# unverified -> verified (accept-preliminary). Terminal states (verified, rejected) cannot be
# re-submitted, re-certified, or re-rejected without a fresh submission cycle.
ALLOWED_SUBMIT_FROM = {"unverified", "in_review", "rejected"}
ALLOWED_CERTIFY_FROM = {"in_review"}
ALLOWED_REJECT_FROM = {"in_review"}
ALLOWED_ACCEPT_PRELIMINARY_FROM = {"unverified"}


class InMemoryVerificationRepository:
    def __init__(self):
        self._records: dict[str, VerificationRecord] = {}

    def get_or_create(self, parcel_id: str, ai_geometry: Polygon) -> VerificationRecord:
        if parcel_id not in self._records:
            rec = VerificationRecord(parcel_id=parcel_id, ai_geometry=ai_geometry)
            rec.log("system", "created", "AI preliminary geometry ingested")
            self._records[parcel_id] = rec
        return self._records[parcel_id]

    def submit_correction(self, parcel_id: str, ai_geometry: Polygon, geojson_geometry: dict,
                           surveyor_name: str, surveyor_license: str, statement: str) -> VerificationRecord:
        # P0-2: validate BEFORE touching any state -- an invalid submission
        # must not create a record, flip status, or overwrite a prior good
        # verified_geometry. validate_surveyor_geometry() raises
        # GeometryValidationError (caught by the API layer -> HTTP 400) on
        # anything that isn't a valid, non-degenerate Polygon.
        validated_geom = validate_surveyor_geometry(geojson_geometry)

        rec = self.get_or_create(parcel_id, ai_geometry)
        if rec.status not in ALLOWED_SUBMIT_FROM:
            raise InvalidTransitionError(rec.status, "submit")
        rec.verified_geometry = validated_geom
        rec.status = "in_review"
        rec.surveyor_name = surveyor_name
        rec.surveyor_license = surveyor_license
        rec.statement = statement
        rec.log(surveyor_name, "submitted_correction", statement or "")
        return rec

    def certify(self, parcel_id: str, surveyor_name: str) -> VerificationRecord:
        rec = self._records[parcel_id]
        if rec.status not in ALLOWED_CERTIFY_FROM:
            raise InvalidTransitionError(rec.status, "certify")
        if rec.verified_geometry is None:
            rec.verified_geometry = rec.ai_geometry  # accepted as-is
        rec.status = "verified"
        rec.log(surveyor_name, "certified", "Boundary signed and certified by surveyor")
        return rec

    def reject(self, parcel_id: str, surveyor_name: str, reason: str) -> VerificationRecord:
        rec = self._records[parcel_id]
        if rec.status not in ALLOWED_REJECT_FROM:
            raise InvalidTransitionError(rec.status, "reject")
        rec.status = "rejected"
        rec.log(surveyor_name, "rejected_ai_output", reason)
        return rec

    def accept_preliminary(self, parcel_id: str, ai_geometry: Polygon, surveyor_name: str) -> VerificationRecord:
        rec = self.get_or_create(parcel_id, ai_geometry)
        if rec.status not in ALLOWED_ACCEPT_PRELIMINARY_FROM:
            raise InvalidTransitionError(rec.status, "accept-preliminary")
        rec.verified_geometry = ai_geometry
        rec.status = "verified"
        rec.log(surveyor_name, "accepted_preliminary", "AI geometry accepted without edits")
        return rec

    def all(self) -> list[VerificationRecord]:
        return list(self._records.values())

    def get(self, parcel_id: str) -> Optional[VerificationRecord]:
        return self._records.get(parcel_id)


VerificationStore = InMemoryVerificationRepository

store = InMemoryVerificationRepository()
