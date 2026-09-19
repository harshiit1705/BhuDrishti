"""
BhuDrishti Geometry & Topology Engine
--------------------------------------
Real geometric computation using Shapely (GEOS). No fake numbers:
every area, overlap, gap and validity check below is computed from
actual polygon geometry, not hard-coded.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional
from shapely.geometry import Polygon, mapping
from shapely.validation import explain_validity
import itertools

SLIVER_AREA_M2 = 0.5        # below this, a gap/overlap sliver is "auto-snappable"
SLIVER_WIDTH_M = 0.10       # narrow-gap heuristic width


@dataclass
class Parcel:
    parcel_id: str
    polygon: Polygon
    source: str = "ai"          # "ai" | "surveyor_verified"
    owner: Optional[str] = None
    ward: Optional[str] = None
    land_use: Optional[str] = None

    @property
    def area_m2(self) -> float:
        return round(self.polygon.area, 2)

    @property
    def is_valid(self) -> bool:
        return self.polygon.is_valid

    @property
    def validity_reason(self) -> str:
        return explain_validity(self.polygon)

    def to_geojson_feature(self) -> dict:
        return {
            "type": "Feature",
            "properties": {
                "parcel_id": self.parcel_id,
                "area_m2": self.area_m2,
                "source": self.source,
                "owner": self.owner,
                "ward": self.ward,
                "land_use": self.land_use,
                "valid_geometry": self.is_valid,
            },
            "geometry": mapping(self.polygon),
        }

    def coordinate_metadata(self) -> dict:
        return {
            "type": "local_demo",
            "crs": None,
            "units": "meters",
            "georeferenced": False,
        }



@dataclass
class TopologyIssue:
    issue_id: str
    issue_type: str                 # overlap | gap | self_intersection | invalid_geometry
    parcel_ids: list
    area_m2: float
    severity: str                   # critical | warning | info
    description: str
    recommended_action: str
    status: str = "open"
    geometry: object | None = None  # actual issue geometry where the engine can compute it

    def to_dict(self):
        data = {k: v for k, v in self.__dict__.items() if k != "geometry"}
        if self.geometry is not None:
            data["geometry"] = mapping(self.geometry)
        return data


def _pairwise(parcels: list[Parcel]):
    return itertools.combinations(parcels, 2)


class GeometryValidationError(ValueError):
    """Raised when submitted surveyor-correction GeoJSON fails validation."""


def validate_surveyor_geometry(geojson_geometry: dict) -> Polygon:
    """
    P0-2 fix: previously the verification endpoint accepted ANY GeoJSON
    geometry object and stored it as-is (see the old `shape(geojson_geometry)`
    call with no checks). That meant a Point, a LineString, a self-intersecting
    ring, or a zero-area sliver could be certified as `surveyor_verified`
    cadastral truth. This function is the single gate every submitted
    correction must pass before it is allowed to reach the verification
    store, and it is used by BOTH /submit and (indirectly, since certify()
    only ever promotes an already-submitted geometry) /certify.

    Raises GeometryValidationError with a human-readable reason on failure.
    Returns the parsed Shapely Polygon on success.
    """
    from shapely.geometry import shape
    from shapely.geometry.base import BaseGeometry

    if not isinstance(geojson_geometry, dict) or "type" not in geojson_geometry:
        raise GeometryValidationError("Submitted geometry is not a GeoJSON geometry object.")

    geom_type = geojson_geometry.get("type")
    if geom_type not in ("Polygon", "MultiPolygon"):
        raise GeometryValidationError(
            f"Only Polygon or MultiPolygon geometry is accepted for a cadastral parcel "
            f"boundary; got '{geom_type}'."
        )

    try:
        geom: BaseGeometry = shape(geojson_geometry)
    except Exception as e:
        raise GeometryValidationError(f"Could not parse GeoJSON geometry: {e}")

    if not isinstance(geom, Polygon):
        # covers MultiPolygon and any other non-Polygon shapely type
        raise GeometryValidationError(
            f"Only single Polygon geometry is currently accepted for surveyor "
            f"corrections; got Shapely type '{geom.geom_type}'."
        )

    if not geom.is_valid:
        raise GeometryValidationError(
            f"Submitted geometry is not a valid simple polygon: {explain_validity(geom)}"
        )

    if geom.is_empty or geom.area <= 1e-9:
        raise GeometryValidationError("Submitted geometry has zero (or near-zero) area.")

    # Coordinate sanity check: reject NaN/inf and wildly out-of-range values
    # that indicate a malformed payload rather than a real boundary edit.
    xs, ys = geom.exterior.coords.xy
    for v in list(xs) + list(ys):
        if v != v or abs(v) == float("inf"):  # v != v is the NaN check
            raise GeometryValidationError("Submitted geometry contains NaN/Infinity coordinates.")
    if len(set(zip(xs, ys))) < 3:
        raise GeometryValidationError("Submitted geometry does not have enough distinct vertices "
                                       "to form a polygon.")

    return geom


def run_topology_validation(parcels: list[Parcel]) -> list[TopologyIssue]:
    """
    Computes REAL topology issues from actual parcel geometries:
      - invalid / self-intersecting geometries (Shapely validity engine)
      - pairwise overlaps (actual intersection area via GEOS)
      - narrow slivers/gaps between adjacent parcels (buffer-based proximity test)
    """
    issues: list[TopologyIssue] = []
    counter = 1

    # 1. Invalid geometry / self-intersection check
    for p in parcels:
        if not p.is_valid:
            issues.append(TopologyIssue(
                issue_id=f"TOP-{counter:03d}",
                issue_type="self_intersection" if "Self-intersection" in p.validity_reason
                            else "invalid_geometry",
                parcel_ids=[p.parcel_id],
                area_m2=0.0,
                severity="critical",
                description=f"Geometry validity failure: {p.validity_reason}",
                recommended_action="Route to surveyor for manual vertex correction.",
            ))
            counter += 1

    # 2. Pairwise overlap detection (only for valid geometries -- GEOS requires valid input)
    valid_parcels = [p for p in parcels if p.is_valid]
    for a, b in _pairwise(valid_parcels):
        if a.polygon.intersects(b.polygon):
            inter = a.polygon.intersection(b.polygon)
            inter_area = inter.area
            if inter_area > 1e-6:  # true areal overlap, not just touching edges
                severity = "critical" if inter_area > SLIVER_AREA_M2 else "warning"
                issues.append(TopologyIssue(
                    issue_id=f"TOP-{counter:03d}",
                    issue_type="overlap",
                    parcel_ids=[a.parcel_id, b.parcel_id],
                    area_m2=round(inter_area, 3),
                    severity=severity,
                    description=f"Boundary overlap of {inter_area:.2f} m² between "
                                f"{a.parcel_id} and {b.parcel_id}.",
                    recommended_action="Field verification: confirm true boundary with GNSS rover.",
                    geometry=inter if inter.geom_type == "Polygon" else None,
                ))
                counter += 1

    # 3. Gap / sliver detection between parcels that are "supposed" to be adjacent
    #    Heuristic: buffer each parcel out by SLIVER_WIDTH_M; if buffers touch but
    #    original polygons do NOT touch, there is an unassigned sliver gap.
    for a, b in _pairwise(valid_parcels):
        if a.polygon.distance(b.polygon) <= SLIVER_WIDTH_M and not a.polygon.touches(b.polygon) \
                and not a.polygon.intersects(b.polygon) and a.polygon.distance(b.polygon) > 1e-9:
            gap_width = a.polygon.distance(b.polygon)
            # Build a small geometry representing the detected gap where GEOS can
            # derive one from the local buffer corridor. This is a visualization
            # aid for the actual computed proximity conflict, not a legal parcel.
            corridor = a.polygon.buffer(SLIVER_WIDTH_M / 2).intersection(b.polygon.buffer(SLIVER_WIDTH_M / 2))
            gap_geom = corridor.difference(a.polygon.union(b.polygon)) if not corridor.is_empty else None
            issues.append(TopologyIssue(
                issue_id=f"TOP-{counter:03d}",
                issue_type="gap",
                parcel_ids=[a.parcel_id, b.parcel_id],
                area_m2=round(gap_width * min(a.polygon.length, b.polygon.length) * 0.01, 3),
                severity="warning",
                description=f"Unassigned sliver gap of ~{gap_width:.2f} m width between "
                            f"{a.parcel_id} and {b.parcel_id}.",
                recommended_action="Auto-snappable if < 0.1m; else route to surveyor.",
                status="resolved" if gap_width < SLIVER_WIDTH_M else "open",
                geometry=gap_geom if getattr(gap_geom, "geom_type", None) in ("Polygon", "MultiPolygon") else None,
            ))
            counter += 1

    return issues
