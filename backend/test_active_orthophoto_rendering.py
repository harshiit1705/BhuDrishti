from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOPOLOGY = (ROOT / "frontend" / "topology-validation.html").read_text(encoding="utf-8")
ELEVATION = (ROOT / "frontend" / "elevation-analysis.html").read_text(encoding="utf-8")
API = (ROOT / "frontend" / "js" / "api-client.js").read_text(encoding="utf-8")

for name, html in (("topology", TOPOLOGY), ("elevation", ELEVATION)):
    assert "Active EXT renderer" in html, f"{name} page lacks the active extraction renderer"
    assert "getExtractionImage" in html, f"{name} page does not restore the extraction image"
    assert "getDatasetImage" in html, f"{name} page does not restore the dataset image"
    assert "Seeded imagery has been disabled" in html, f"{name} page can silently fall back to seeded imagery"

assert "saveExtractionImage" in API and "saveDatasetImage" in API
assert "getDatasetFileUrl" in API
assert "No real DSM/DTM is attached" in ELEVATION
assert "NOT CALCULATED FOR THIS UPLOAD" in TOPOLOGY
print("ACTIVE ORTHOPHOTO RENDERING CONTRACT: PASS")
