"""
Extraction record store -- holds AI-generated preliminary geometry produced
by extraction_engine.run_cv_inference(), kept SEPARATE from the seeded demo
`PARCELS` dict in main.py so real inference output is never confused with,
or silently mutates, the fixture data.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime, timezone
from shapely.geometry import Polygon, mapping


@dataclass
class ExtractionRecord:
    extraction_id: str
    source_filename: str
    geometry: Polygon
    image_width: int
    image_height: int
    image_format: str
    confidence_heuristic: float
    pixel_polygon: list
    inference_mode: str
    notes: str
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    status: str = "ai_preliminary"   # distinct from verification_store's parcel-verification states
    is_demo_data: bool = False

    @property
    def area_m2(self) -> float:
        return round(self.geometry.area, 2)

    def to_dict(self) -> dict:
        return {
            "extraction_id": self.extraction_id,
            "source_filename": self.source_filename,
            "geometry": mapping(self.geometry),
            "area_m2": self.area_m2,
            "image_width": self.image_width,
            "image_height": self.image_height,
            "image_format": self.image_format,
            "confidence_heuristic": self.confidence_heuristic,
            "pixel_polygon": self.pixel_polygon,
            "inference_mode": self.inference_mode,
            "notes": self.notes,
            "created_at": self.created_at,
            "status": self.status,
            "is_demo_data": self.is_demo_data,
        }


class ExtractionStore:
    def __init__(self):
        self._records: dict[str, ExtractionRecord] = {}
        self._counter = 0

    def new_id(self) -> str:
        self._counter += 1
        return f"EXT-{self._counter:04d}"

    def save(self, record: ExtractionRecord) -> ExtractionRecord:
        self._records[record.extraction_id] = record
        return record

    def get(self, extraction_id: str) -> ExtractionRecord | None:
        return self._records.get(extraction_id)

    def all(self) -> list[ExtractionRecord]:
        return list(self._records.values())


extraction_store = ExtractionStore()
