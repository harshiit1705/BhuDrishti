"""Sprint 4 regression tests: shadow/elevation differentiation prototype."""
from backend.app.main import _shadow_for, get_shadow
from backend.app.shadow_engine import analyze_shadow, prototype_surface_from_pixel_polygon
import numpy as np
from shapely.geometry import Polygon


def main():
    # 1. Seeded elevation anomaly produces real shadow evidence.
    bd019 = _shadow_for("BD-019")
    assert bd019 is not None
    assert bd019.shadow_consistency_score > 0
    assert bd019.predicted_shadow_length_m > 0
    assert bd019.estimated_overhang_m > 0
    assert bd019.boundary_adjustment_candidate["available"] is True
    assert bd019.is_demo_data is True

    # 2. A different sun vector changes the projected shadow direction/length.
    altered = _shadow_for("BD-019", sun_azimuth_deg=220.0, sun_elevation_deg=55.0)
    assert altered.shadow_direction_deg != bd019.shadow_direction_deg
    assert altered.predicted_shadow_length_m < bd019.predicted_shadow_length_m

    # 3. Direct raster calculation is deterministic and produces a bounded score.
    dsm = np.zeros((32, 32), dtype=float)
    dtm = np.zeros((32, 32), dtype=float)
    dsm[8:24, 8:24] = 8.0
    r1 = analyze_shadow("TEST", dsm, dtm, roof_polygon=Polygon([(2,2),(5,2),(5,5),(2,5)]))
    r2 = analyze_shadow("TEST", dsm, dtm, roof_polygon=Polygon([(2,2),(5,2),(5,5),(2,5)]))
    assert r1.shadow_consistency_score == r2.shadow_consistency_score
    assert 0 <= r1.shadow_consistency_score <= 100
    assert 0 <= r1.evidence_confidence <= 100

    # 4. Uploaded-image bridge: synthetic DSM follows the actual CV polygon.
    dsm2, dtm2 = prototype_surface_from_pixel_polygon(
        [[10,10],[50,10],[50,50],[10,50]], 64, 64, size=32
    )
    assert float((dsm2-dtm2).max()) >= 7.0

    # 5. Public route shape exposes the new evidence endpoint.
    payload = get_shadow("BD-019", 142.4, 38.1)
    assert payload["model_status"] == "PROTOTYPE_PHYSICS_INSPIRED"
    assert payload["authoritative_boundary"] is False
    assert payload["source"] == "sprint4_shadow_evidence"

    print("SPRINT 4 DIFFERENTIATION: PASS")


if __name__ == "__main__":
    main()
