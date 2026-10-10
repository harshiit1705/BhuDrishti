"""
BhuDrishti Sprint 4 -- shadow / elevation evidence engine.

This is a physically-inspired prototype, not a legal cadastral correction engine.
It uses:
  1. DSM - DTM (nDSM) to locate elevated structure pixels;
  2. a supplied sun azimuth/elevation to project a cast-shadow candidate;
  3. an orthophoto luminance image when one is available;
  4. otherwise a deterministic synthetic paired orthophoto for demo parcels;
  5. shadow/brightness agreement to estimate evidence strength;
  6. a preliminary inward boundary adjustment candidate.

All coordinates are raster-local in this sprint. No CRS transformation or solar
ephemeris lookup is performed. The returned candidate is advisory only.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
import hashlib
from typing import Optional

import numpy as np
from shapely.geometry import Polygon, Point


DEFAULT_SUN_AZIMUTH_DEG = 142.4
DEFAULT_SUN_ELEVATION_DEG = 38.1
DEFAULT_GSD_M_PER_PX = 0.05


def prototype_surface_from_pixel_polygon(pixel_polygon: list[list[float]], image_width: int, image_height: int,
                                         *, size: int = 64, ground_m: float = 100.0, height_m: float = 7.0):
    """Create a synthetic DSM/DTM whose elevated mask follows the actual CV polygon.

    This intentionally bridges the real uploaded image and the Sprint-4 shadow
    calculation without claiming that the uploaded image contains a measured DSM.
    """
    if not pixel_polygon or image_width <= 0 or image_height <= 0:
        raise ValueError("pixel polygon and image dimensions are required")
    pts = np.asarray(pixel_polygon, dtype=float)
    if pts.ndim != 2 or pts.shape[1] != 2:
        raise ValueError("pixel polygon must contain [x, y] points")
    sx = (size - 1) / max(1.0, float(image_width - 1))
    sy = (size - 1) / max(1.0, float(image_height - 1))
    scaled = np.column_stack((pts[:, 0] * sx, pts[:, 1] * sy))
    yy, xx = np.mgrid[0:size, 0:size]
    poly = Polygon([(float(x), float(y)) for x, y in scaled])
    if not poly.is_valid:
        poly = poly.buffer(0)
    inside = np.zeros((size, size), dtype=bool)
    if not poly.is_empty:
        # Point-in-polygon is adequate for the small deterministic prototype grid.
        for y in range(size):
            for x in range(size):
                inside[y, x] = poly.covers(Point(float(x), float(y)))
    rng = np.random.default_rng(17 + int(image_width) + int(image_height))
    dtm = ground_m + rng.normal(0, 0.02, (size, size))
    dsm = dtm.copy()
    dsm[inside] += height_m
    return dsm, dtm


@dataclass
class ShadowAnalysisResult:
    parcel_id: str
    sun_azimuth_deg: float
    sun_elevation_deg: float
    shadow_direction_deg: float
    predicted_shadow_length_m: float
    predicted_shadow_length_px: float
    elevated_pixel_count: int
    predicted_shadow_pixel_count: int
    observed_dark_pixel_count: int
    shadow_iou: float
    shadow_contrast_score: float
    shadow_consistency_score: float
    estimated_overhang_m: float
    boundary_adjustment_distance_m: float
    boundary_adjustment_direction_deg: float
    boundary_adjustment_candidate: dict
    evidence_confidence: float
    source_mode: str
    is_demo_data: bool
    notes: str


def _shift_mask(mask: np.ndarray, dx: int, dy: int) -> np.ndarray:
    """Shift a boolean raster without wrapping pixels around the opposite edge."""
    out = np.zeros_like(mask, dtype=bool)
    h, w = mask.shape
    src_x0 = max(0, -dx)
    src_x1 = min(w, w - dx) if dx >= 0 else w
    src_y0 = max(0, -dy)
    src_y1 = min(h, h - dy) if dy >= 0 else h
    dst_x0 = max(0, dx)
    dst_x1 = dst_x0 + max(0, src_x1 - src_x0)
    dst_y0 = max(0, dy)
    dst_y1 = dst_y0 + max(0, src_y1 - src_y0)
    if src_x1 <= src_x0 or src_y1 <= src_y0:
        return out
    out[dst_y0:dst_y1, dst_x0:dst_x1] = mask[src_y0:src_y1, src_x0:src_x1]
    return out


def project_shadow(elevated_mask: np.ndarray, height_m: float, sun_azimuth_deg: float,
                   sun_elevation_deg: float, gsd_m_per_px: float) -> tuple[np.ndarray, float, float]:
    """Project a first-order cast-shadow mask from an elevated surface."""
    if sun_elevation_deg <= 1.0 or sun_elevation_deg >= 89.9:
        raise ValueError("sun_elevation_deg must be between 1 and 89.9 degrees")
    gsd = max(float(gsd_m_per_px), 1e-6)
    shadow_len_m = max(0.0, float(height_m)) / math.tan(math.radians(float(sun_elevation_deg)))
    shadow_len_px = shadow_len_m / gsd

    # Raster convention: x=east/right, y=south/down. The shadow travels
    # opposite the sun azimuth, so subtract the sun vector.
    theta = math.radians(float(sun_azimuth_deg))
    dx = int(round(-math.sin(theta) * shadow_len_px))
    dy = int(round(math.cos(theta) * shadow_len_px))
    projected = _shift_mask(elevated_mask, dx, dy)
    # Do not count the elevated footprint itself as cast shadow evidence.
    projected &= ~elevated_mask
    return projected, shadow_len_m, shadow_len_px


def _dark_mask(luminance: np.ndarray, percentile: float = 25.0) -> np.ndarray:
    threshold = float(np.percentile(luminance, percentile))
    return luminance <= threshold


def _contrast_score(luminance: np.ndarray, predicted_shadow: np.ndarray) -> float:
    if not predicted_shadow.any():
        return 0.0
    inside = luminance[predicted_shadow]
    outside = luminance[~predicted_shadow]
    if inside.size == 0 or outside.size == 0:
        return 0.0
    # 0 when the candidate shadow is no darker than its surroundings,
    # 100 when it is substantially darker (normalized over an 80-level span).
    contrast = float(np.mean(outside) - np.mean(inside))
    return float(np.clip((contrast / 80.0) * 100.0, 0.0, 100.0))


def _polygon_adjustment_candidate(roof_polygon: Polygon, distance_m: float, direction_deg: float) -> dict:
    """Return a local advisory polygon; never label it as a legal boundary."""
    if roof_polygon.is_empty or not roof_polygon.is_valid:
        return {"available": False, "reason": "Roof candidate geometry is unavailable or invalid."}
    d = max(0.0, min(float(distance_m), 5.0))
    # The candidate footprint is a conservative inward buffer. Direction is
    # reported separately because a polygon buffer cannot encode directional
    # displacement by itself without a full affine/vector model.
    candidate = roof_polygon.buffer(-d)
    if candidate.is_empty or not candidate.is_valid:
        candidate = roof_polygon
    return {
        "available": True,
        "geometry_type": candidate.geom_type,
        "geometry": candidate.__geo_interface__,
        "method": "inward_roof_buffer_with_shadow_direction_metadata",
        "distance_m": round(d, 3),
        "direction_deg": round(float(direction_deg) % 360.0, 1),
        "status": "PRELIMINARY_CANDIDATE",
        "legal_boundary": False,
    }


def analyze_shadow(parcel_id: str, dsm: np.ndarray, dtm: np.ndarray,
                   *, sun_azimuth_deg: float = DEFAULT_SUN_AZIMUTH_DEG,
                   sun_elevation_deg: float = DEFAULT_SUN_ELEVATION_DEG,
                   gsd_m_per_px: float = DEFAULT_GSD_M_PER_PX,
                   luminance: Optional[np.ndarray] = None,
                   roof_polygon: Optional[Polygon] = None,
                   source_mode: str = "synthetic_paired_demo") -> ShadowAnalysisResult:
    if dsm.shape != dtm.shape:
        raise ValueError("DSM and DTM grids must share the same shape")
    ndsm = dsm - dtm
    elevated = ndsm >= 1.0
    if not elevated.any():
        raise ValueError("No elevated structure pixels found in nDSM")

    height = float(np.percentile(ndsm[elevated], 90))
    predicted, shadow_len_m, shadow_len_px = project_shadow(
        elevated, height, sun_azimuth_deg, sun_elevation_deg, gsd_m_per_px
    )

    if luminance is None:
        # Deterministic paired orthophoto: medium-bright ground, bright roof,
        # and a dark cast shadow generated from the same physical sun vector.
        seed = int(hashlib.sha1(parcel_id.encode("utf-8")).hexdigest()[:8], 16)
        rng = np.random.default_rng(seed)
        luminance = np.full(dsm.shape, 155.0, dtype=np.float32)
        luminance += rng.normal(0.0, 7.0, dsm.shape)
        luminance[elevated] = 205.0 + rng.normal(0.0, 5.0, int(elevated.sum()))
        luminance[predicted] = 48.0 + rng.normal(0.0, 5.0, int(predicted.sum()))
        source_mode = "synthetic_paired_demo"
    else:
        if luminance.ndim != 2:
            raise ValueError("Orthophoto luminance must be a 2-D array")
        if luminance.shape != dsm.shape:
            # A production implementation would resample using the DSM's
            # georeferencing. Sprint 4 deliberately does not pretend to do so.
            source_mode = "orthophoto_size_mismatch_fallback"
            luminance = None
            return analyze_shadow(parcel_id, dsm, dtm,
                                  sun_azimuth_deg=sun_azimuth_deg,
                                  sun_elevation_deg=sun_elevation_deg,
                                  gsd_m_per_pixel=gsd_m_per_px,
                                  luminance=None,
                                  roof_polygon=roof_polygon,
                                  source_mode=source_mode)
        luminance = luminance.astype(np.float32)

    dark = _dark_mask(luminance)
    inter = int(np.logical_and(predicted, dark).sum())
    union = int(np.logical_or(predicted, dark).sum())
    iou = float(inter / union) if union else 0.0
    contrast = _contrast_score(luminance, predicted)
    consistency = float(np.clip(0.65 * iou * 100.0 + 0.35 * contrast, 0.0, 100.0))

    # Convert shadow consistency into a conservative overhang proxy. A weak
    # shadow match must not create a large correction candidate.
    estimated_overhang_m = min(shadow_len_m * 0.20, 2.0) * (consistency / 100.0)
    direction = (float(sun_azimuth_deg) + 180.0) % 360.0
    candidate = _polygon_adjustment_candidate(roof_polygon, estimated_overhang_m, direction) if roof_polygon else {
        "available": False,
        "reason": "No roof polygon supplied; raster evidence only."
    }

    confidence = float(np.clip(0.70 * consistency + 30.0 * min(1.0, height / 10.0), 0.0, 100.0))
    return ShadowAnalysisResult(
        parcel_id=parcel_id,
        sun_azimuth_deg=round(float(sun_azimuth_deg), 1),
        sun_elevation_deg=round(float(sun_elevation_deg), 1),
        shadow_direction_deg=round(direction, 1),
        predicted_shadow_length_m=round(shadow_len_m, 3),
        predicted_shadow_length_px=round(shadow_len_px, 1),
        elevated_pixel_count=int(elevated.sum()),
        predicted_shadow_pixel_count=int(predicted.sum()),
        observed_dark_pixel_count=int(dark.sum()),
        shadow_iou=round(iou, 4),
        shadow_contrast_score=round(contrast, 1),
        shadow_consistency_score=round(consistency, 1),
        estimated_overhang_m=round(estimated_overhang_m, 3),
        boundary_adjustment_distance_m=round(estimated_overhang_m, 3),
        boundary_adjustment_direction_deg=round(direction, 1),
        boundary_adjustment_candidate=candidate,
        evidence_confidence=round(confidence, 1),
        source_mode=source_mode,
        is_demo_data=source_mode.startswith("synthetic"),
        notes=("Prototype shadow/elevation evidence: nDSM identifies elevated structure, "
               "a supplied sun vector projects a cast-shadow candidate, and luminance "
               "agreement estimates evidence strength. No solar ephemeris, CRS transform, "
               "or authoritative cadastral correction is performed. The boundary candidate "
               "is advisory and requires surveyor verification."),
    )
