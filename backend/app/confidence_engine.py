"""
BhuDrishti Confidence / Risk Engine
------------------------------------
Transparent, documented weighted-sum model. NOT a black box: every
factor and weight is listed here and returned to the caller so the
frontend can show "why" a parcel scored the way it did.

confidence = 100 - risk_score  (both 0-100)

risk_score = w_topo * topo_component
           + w_geom * geometric_irregularity_component
           + w_elev * elevation_disagreement_component
           + w_hist * historical_mismatch_component

Weights sum to 1.0 and are configurable in RISK_WEIGHTS below.
"""
from __future__ import annotations
from dataclasses import dataclass

RISK_WEIGHTS = {
    "topology": 0.40,
    "geometric_irregularity": 0.20,
    "elevation_disagreement": 0.25,
    "historical_mismatch": 0.15,
}

# Configurable survey-priority thresholds (per project requirement: "must be
# configurable rather than hard-coded everywhere" -- this is the single
# source of truth other modules import from).
PRIORITY_THRESHOLDS = {
    "high": 60,     # risk_score >= 60  -> immediate field verification
    "medium": 30,   # 30 <= risk_score < 60 -> desk / secondary review
    # risk_score < 30 -> autonomous sign-off
}


@dataclass
class ConfidenceBreakdown:
    parcel_id: str
    topology_component: float        # 0-100, higher = worse
    geometric_component: float
    elevation_component: float
    historical_component: float
    risk_score: float
    confidence: float
    priority: str
    reasons: list

    def to_dict(self):
        return {
            "parcel_id": self.parcel_id,
            "confidence": round(self.confidence, 1),
            "risk_score": round(self.risk_score, 1),
            "priority": self.priority,
            "factors": {
                "topology": round(self.topology_component, 1),
                "geometric_irregularity": round(self.geometric_component, 1),
                "elevation_disagreement": round(self.elevation_component, 1),
                "historical_mismatch": round(self.historical_component, 1),
            },
            "weights": RISK_WEIGHTS,
            "reasons": self.reasons,
        }


def priority_for_score(risk_score: float) -> str:
    if risk_score >= PRIORITY_THRESHOLDS["high"]:
        return "high"
    if risk_score >= PRIORITY_THRESHOLDS["medium"]:
        return "medium"
    return "low"


def compute_confidence(parcel_id: str, *, has_overlap: bool, has_gap: bool,
                        has_invalid_geometry: bool, irregularity_ratio: float,
                        ndsm_disagreement_m: float, historical_shift_m: float) -> ConfidenceBreakdown:
    """
    irregularity_ratio: 0 (perfectly regular/rectangular) .. 1 (very irregular),
        derived elsewhere from polygon min_rotated_rect area ratio.
    ndsm_disagreement_m: abs(overhang offset) from elevation engine.
    historical_shift_m: distance between AI boundary and legacy revenue map, if available.
    """
    reasons = []

    topo_component = 0.0
    if has_invalid_geometry:
        topo_component = 100.0
        reasons.append("Invalid/self-intersecting geometry")
    elif has_overlap:
        topo_component = 80.0
        reasons.append("Boundary overlap with neighboring parcel")
    elif has_gap:
        topo_component = 35.0
        reasons.append("Unassigned sliver gap detected")

    geometric_component = min(100.0, irregularity_ratio * 100.0)
    if irregularity_ratio > 0.35:
        reasons.append(f"Irregular boundary shape (irregularity={irregularity_ratio:.2f})")

    elevation_component = min(100.0, (ndsm_disagreement_m / 1.5) * 100.0)
    if ndsm_disagreement_m > 0.3:
        reasons.append(f"DSM/DTM overhang offset of {ndsm_disagreement_m:.2f} m")

    historical_component = min(100.0, (historical_shift_m / 2.0) * 100.0)
    if historical_shift_m > 0.5:
        reasons.append(f"Legacy revenue map deviates {historical_shift_m:.2f} m from AI boundary")

    risk_score = (
        RISK_WEIGHTS["topology"] * topo_component +
        RISK_WEIGHTS["geometric_irregularity"] * geometric_component +
        RISK_WEIGHTS["elevation_disagreement"] * elevation_component +
        RISK_WEIGHTS["historical_mismatch"] * historical_component
    )
    confidence = 100.0 - risk_score

    if not reasons:
        reasons.append("No topology, elevation, or historical conflicts detected")

    return ConfidenceBreakdown(
        parcel_id=parcel_id,
        topology_component=topo_component,
        geometric_component=geometric_component,
        elevation_component=elevation_component,
        historical_component=historical_component,
        risk_score=risk_score,
        confidence=confidence,
        priority=priority_for_score(risk_score),
        reasons=reasons,
    )
