"""
BhuDrishti Elevation Engine
---------------------------
Implements nDSM = DSM - DTM using real numpy raster arrays.

NOTE ON FIDELITY (read this before trusting the numbers elsewhere):
This environment does not have GDAL/rasterio available (no network
access to system packages, only pip index). So we cannot ingest real
GeoTIFF DSM/DTM files here. Instead we generate small synthetic
raster grids (numpy arrays with a known, documented elevation
surface) that stand in for a DSM and DTM pair for each demo parcel.
The nDSM subtraction, height statistics, and overhang-offset logic
below are REAL computations on those arrays -- nothing is a hard-coded
"display number". If BhuDrishti is deployed on demo hardware where
GDAL/rasterio can be installed, swap `load_raster()` for a real
rasterio read and everything downstream keeps working unchanged.
"""
from __future__ import annotations
from dataclasses import dataclass
import numpy as np


@dataclass
class ElevationResult:
    parcel_id: str
    dsm_mean_m: float
    dtm_mean_m: float
    ndsm_mean_m: float          # normalized height = DSM - DTM
    ndsm_max_m: float
    estimated_floors: int
    overhang_offset_m: float    # horizontal parallax proxy (see note)
    notes: str


def synth_raster_pair(seed: int, base_ground_m: float, building_height_m: float,
                       size: int = 32, overhang_px: int = 0):
    """
    Build a deterministic synthetic DSM/DTM grid pair for one parcel.
    DTM = flat bare-earth baseline (+ tiny deterministic noise).
    DSM = DTM + a raised "building" plateau covering most of the grid,
          with an optional shifted overhang footprint (models roof
          eave capture beyond true wall footing).
    Deterministic (seeded) so results are reproducible run-to-run,
    per project requirement.
    """
    rng = np.random.default_rng(seed)
    dtm = base_ground_m + rng.normal(0, 0.02, (size, size))  # ±2cm ground noise

    dsm = dtm.copy()
    core = slice(size // 6, size - size // 6)
    dsm[core, core] += building_height_m

    if overhang_px:
        shifted = slice(size // 6 - overhang_px, size - size // 6 - overhang_px)
        dsm[core, shifted] += building_height_m * 0.15  # partial eave elevation bleed

    return dsm, dtm


def analyze_parcel_elevation(parcel_id: str, dsm: np.ndarray, dtm: np.ndarray,
                              overhang_offset_m: float = 0.0) -> ElevationResult:
    if dsm.shape != dtm.shape:
        raise ValueError("DSM and DTM grids must share the same shape to compute nDSM.")

    ndsm = dsm - dtm  # the actual differential computation
    ndsm_mean = float(np.mean(ndsm[ndsm > 0.15]) if np.any(ndsm > 0.15) else np.mean(ndsm))
    ndsm_max = float(np.max(ndsm))
    floors = max(0, round(ndsm_max / 3.0))  # ~3m per storey, standard assumption

    return ElevationResult(
        parcel_id=parcel_id,
        dsm_mean_m=round(float(np.mean(dsm)), 3),
        dtm_mean_m=round(float(np.mean(dtm)), 3),
        ndsm_mean_m=round(ndsm_mean, 3),
        ndsm_max_m=round(ndsm_max, 3),
        estimated_floors=floors,
        overhang_offset_m=round(overhang_offset_m, 3),
        notes=("nDSM computed as DSM-DTM over synthetic demo raster grid. "
               "overhang_offset_m is a configured demo parameter representing "
               "horizontal roof-eave vs ground-footing displacement; in a "
               "production build this would come from sun-angle back-projection "
               "over a real DSM, not a synthetic grid."),
    )
