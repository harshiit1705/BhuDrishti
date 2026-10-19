"""Persistent extraction repository backed by local SQLite or managed PostgreSQL.

Geometry is stored as WKT and rich candidate metadata as JSON. Schema changes are
owned by the explicit migration runner, not repository construction.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime, timezone
import json
from shapely.geometry import Polygon, mapping
from shapely import wkt

from .persistence import DB_PATH
from .database import connect_db, is_postgres


def _conn():
    return connect_db(DB_PATH)


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
    parcel_candidates: list = field(default_factory=list)
    roof_footprints: list = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    status: str = "ai_preliminary"
    is_demo_data: bool = False
    dataset_id: str | None = None

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
            "parcel_candidates": self.parcel_candidates,
            "roof_footprints": self.roof_footprints,
            "inference_mode": self.inference_mode,
            "notes": self.notes,
            "created_at": self.created_at,
            "status": self.status,
            "is_demo_data": self.is_demo_data,
            "dataset_id": self.dataset_id,
        }


class PersistentExtractionRepository:
    def __init__(self):
        # Schema is initialized centrally (locally at app startup; in production
        # by the explicit migration command). Constructors must never issue DDL.
        self.db_path = DB_PATH

    def new_id(self) -> str:
        with _conn() as c:
            if is_postgres():
                row = c.execute("SELECT nextval('extraction_id_seq') AS next_id").fetchone()
                return f"EXT-{int(row['next_id']):04d}"
            row = c.execute("SELECT extraction_id FROM extractions WHERE extraction_id GLOB 'EXT-[0-9]*' ORDER BY CAST(substr(extraction_id,5) AS INTEGER) DESC LIMIT 1").fetchone()
        n = int(row["extraction_id"][4:]) + 1 if row else 1
        return f"EXT-{n:04d}"

    def save(self, record: ExtractionRecord) -> ExtractionRecord:
        with _conn() as c:
            c.execute("""INSERT INTO extractions (
                extraction_id, source_filename, geometry_wkt, image_width, image_height,
                image_format, confidence_heuristic, pixel_polygon_json, inference_mode, notes,
                parcel_candidates_json, roof_footprints_json, created_at, status, is_demo_data, dataset_id
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(extraction_id) DO UPDATE SET
                source_filename=excluded.source_filename, geometry_wkt=excluded.geometry_wkt,
                image_width=excluded.image_width, image_height=excluded.image_height,
                image_format=excluded.image_format, confidence_heuristic=excluded.confidence_heuristic,
                pixel_polygon_json=excluded.pixel_polygon_json, inference_mode=excluded.inference_mode,
                notes=excluded.notes, parcel_candidates_json=excluded.parcel_candidates_json,
                roof_footprints_json=excluded.roof_footprints_json, created_at=excluded.created_at,
                status=excluded.status, is_demo_data=excluded.is_demo_data, dataset_id=excluded.dataset_id""", (
                record.extraction_id, record.source_filename, record.geometry.wkt,
                record.image_width, record.image_height, record.image_format,
                record.confidence_heuristic, json.dumps(record.pixel_polygon), record.inference_mode,
                record.notes, json.dumps(record.parcel_candidates), json.dumps(record.roof_footprints),
                record.created_at, record.status, int(record.is_demo_data), record.dataset_id))
        return record

    def _row(self, row):
        if not row: return None
        return ExtractionRecord(
            extraction_id=row["extraction_id"], source_filename=row["source_filename"],
            geometry=wkt.loads(row["geometry_wkt"]), image_width=row["image_width"], image_height=row["image_height"],
            image_format=row["image_format"], confidence_heuristic=row["confidence_heuristic"],
            pixel_polygon=json.loads(row["pixel_polygon_json"] or "[]"), inference_mode=row["inference_mode"],
            notes=row["notes"], parcel_candidates=json.loads(row["parcel_candidates_json"] or "[]"),
            roof_footprints=json.loads(row["roof_footprints_json"] or "[]"), created_at=row["created_at"],
            status=row["status"], is_demo_data=bool(row["is_demo_data"]), dataset_id=row["dataset_id"])

    def get(self, extraction_id: str):
        with _conn() as c: return self._row(c.execute("SELECT * FROM extractions WHERE extraction_id=?", (extraction_id,)).fetchone())

    def all(self):
        order = "CASE WHEN extraction_id ~ '^EXT-[0-9]+$' THEN CAST(substring(extraction_id from 5) AS BIGINT) ELSE 2147483647 END, extraction_id" if is_postgres() else "CASE WHEN extraction_id GLOB 'EXT-[0-9]*' THEN CAST(substr(extraction_id,5) AS INTEGER) ELSE 2147483647 END, extraction_id"
        with _conn() as c: return [self._row(r) for r in c.execute(f"SELECT * FROM extractions ORDER BY {order}").fetchall()]

    def update_status(self, extraction_id: str, status: str):
        with _conn() as c: c.execute("UPDATE extractions SET status=? WHERE extraction_id=?", (status, extraction_id))


ExtractionStore = PersistentExtractionRepository
extraction_store = PersistentExtractionRepository()
