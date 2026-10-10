"""Sprint 2 backend correctness regression checks.
Run from repo root with: python backend/test_sprint2_backend_correctness.py
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.app.main import _authoritative_parcels, _issues_by_parcel, _confidence_for_geometry, _target_elevation
from backend.app.geometry_engine import run_topology_validation

parcels = _authoritative_parcels()
issues = run_topology_validation(parcels)
by = _issues_by_parcel(issues)
lookup = {p.parcel_id: p for p in parcels}

# BD-047 was the known regression: elevation/history must now contribute.
c = _confidence_for_geometry("BD-047", lookup["BD-047"], by)
assert round(c.risk_score, 1) == 63.1, c.to_dict()
assert round(c.confidence, 1) == 36.9, c.to_dict()
assert c.priority == "high", c.to_dict()
assert c.to_dict()["factors"]["elevation_disagreement"] > 0
assert c.to_dict()["factors"]["historical_mismatch"] > 0
assert any("DSM/DTM overhang" in r for r in c.reasons)
assert any("Legacy revenue map" in r for r in c.reasons)

# BD-019 is the elevation-only anomaly and must no longer be 100% confidence.
c19 = _confidence_for_geometry("BD-019", lookup["BD-019"], by)
assert round(c19.risk_score, 1) == 18.8, c19.to_dict()
assert c19.confidence < 100
assert c19.priority == "low"

# Invalid topology remains high priority.
c82 = _confidence_for_geometry("BD-082", lookup["BD-082"], by)
assert c82.priority == "high"
assert c82.to_dict()["factors"]["topology"] == 100.0

# Same evaluator exposes the deterministic elevation input used by risk.
e = _target_elevation("BD-047")
assert e is not None and round(e.overhang_offset_m, 2) == 1.37

print("SPRINT 2 BACKEND CORRECTNESS: PASS")
print("BD-047:", c.to_dict())
print("BD-019:", c19.to_dict())
print("BD-082:", c82.to_dict())
