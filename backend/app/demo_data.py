"""
Deterministic demo/sample dataset for BhuDrishti.

THIS IS SYNTHETIC DEMO DATA -- explicitly labeled as such everywhere it
is surfaced via the API (see `is_demo_data: true` in every response).
It is NOT real government cadastral data and must never be presented
as such (see project instructions, "GOVERNMENT INTEGRATIONS" section).

Six intentionally engineered cases, as required:
  1. BD-001  Normal high-confidence parcel
  2. BD-047 / BD-048  Overlapping parcels
  3. BD-103 / BD-104  Sliver / gap
  4. BD-082  Geometry inconsistency (self-intersecting bowtie)
  5. BD-019  Building/elevation anomaly (roof overhang beyond footing)
  6. BD-047  (reused) High-risk parcel requiring surveyor verification
     -- BD-047 combines overlap + elevation anomaly so it is the
        clear "send to field" example for the 90s demo.
"""
from shapely.geometry import Polygon
from .geometry_engine import Parcel

PROJECT_ID = "SIH-2026-IND-U04"
PROJECT_NAME = "Indore Urban Zone 04 — Scheme 54"
CRS = "EPSG:32643"


def build_demo_parcels() -> list[Parcel]:
    parcels = []

    # 1. Normal high-confidence rectangular parcel
    parcels.append(Parcel(
        parcel_id="BD-001", source="ai", owner="Smt. Rukmani Devi",
        ward="Ward 14", land_use="Residential",
        polygon=Polygon([(0, 0), (12, 0), (12, 10), (0, 10)]),
    ))

    # 2. Overlapping parcel pair BD-047 / BD-048 (deliberate 1.2m encroachment)
    parcels.append(Parcel(
        parcel_id="BD-047", source="ai", owner="Anand Commercial Mart Ltd.",
        ward="Ward 18", land_use="Residential",
        polygon=Polygon([(50, 0), (61, 0), (61, 10), (50, 10)]),
    ))
    parcels.append(Parcel(
        parcel_id="BD-048", source="ai", owner="Shri Ramchandra Verma",
        ward="Ward 18", land_use="Residential",
        # starts 1.2m inside BD-047's eastern boundary -> real overlap
        polygon=Polygon([(59.8, 0), (72, 0), (72, 10), (59.8, 10)]),
    ))

    # 3. Sliver / gap pair BD-103 / BD-104 (0.06m gap -- below auto-snap threshold)
    parcels.append(Parcel(
        parcel_id="BD-103", source="ai", owner="Ward 15 Plot Holder",
        ward="Ward 15", land_use="Residential",
        polygon=Polygon([(100, 0), (110, 0), (110, 10), (100, 10)]),
    ))
    parcels.append(Parcel(
        parcel_id="BD-104", source="ai", owner="Adjoining Plot Holder",
        ward="Ward 15", land_use="Residential",
        polygon=Polygon([(110.06, 0), (120, 0), (120, 10), (110.06, 10)]),
    ))

    # 4. Self-intersecting bowtie geometry (genuinely invalid per GEOS)
    parcels.append(Parcel(
        parcel_id="BD-082", source="ai", owner="N/A (Internal defect)",
        ward="Ward 14", land_use="Residential",
        polygon=Polygon([(150, 0), (160, 10), (150, 10), (160, 0)]),  # bowtie
    ))

    # 5. Building/elevation anomaly: valid, non-overlapping geometry but
    #    a large roof overhang beyond the ground footing (flagged via elevation engine)
    parcels.append(Parcel(
        parcel_id="BD-019", source="ai", owner="Ward 14 Plot 31",
        ward="Ward 14", land_use="Residential",
        polygon=Polygon([(200, 0), (212, 0), (212, 10), (200, 10)]),
    ))

    return parcels


# Per-parcel elevation demo config: (seed, ground_elev_m, building_height_m, overhang_px, overhang_offset_m)
ELEVATION_DEMO_CONFIG = {
    "BD-001": dict(seed=1, ground_m=550.0, height_m=6.0, overhang_px=0, overhang_offset_m=0.05),
    "BD-047": dict(seed=47, ground_m=553.2, height_m=8.6, overhang_px=3, overhang_offset_m=1.37),
    "BD-048": dict(seed=48, ground_m=553.0, height_m=6.5, overhang_px=0, overhang_offset_m=0.10),
    "BD-103": dict(seed=103, ground_m=551.5, height_m=5.0, overhang_px=0, overhang_offset_m=0.02),
    "BD-104": dict(seed=104, ground_m=551.4, height_m=5.2, overhang_px=0, overhang_offset_m=0.02),
    "BD-082": dict(seed=82, ground_m=552.0, height_m=0.0, overhang_px=0, overhang_offset_m=0.0),
    "BD-019": dict(seed=19, ground_m=549.8, height_m=7.2, overhang_px=4, overhang_offset_m=0.95),
}

# Historical (legacy Khasra 1984) boundary shift, meters, per parcel (demo values)
HISTORICAL_SHIFT_DEMO_M = {
    "BD-001": 0.05,
    "BD-047": 1.10,
    "BD-048": 0.30,
    "BD-103": 0.10,
    "BD-104": 0.10,
    "BD-082": 0.0,
    "BD-019": 0.40,
}
