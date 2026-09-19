"""Persistent extraction repository for the prototype.

Uses SQLite so uploaded extraction records survive page navigation, refresh,
and backend restarts. Geometry is stored as WKT and rich candidate metadata as JSON.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime, timezone
import json
import sqlite3
from pathlib import Path
from shapely.geometry import Polygon, mapping
from shapely import wkt

# Vercel serverless functions run from a read-only deployment filesystem.
# Keep the prototype SQLite file in /tmp there; local development keeps the
# durable project-local path. /tmp is writable but is not durable across
# serverless instances, so this is prototype persistence only.
if __import__("os").environ.get("VERCEL"):
    DB_PATH = Path("/tmp/bhudrishti") / "bhudrishti.db"
else:
    DB_PATH = Path(__file__).resolve().parent.parent / "data" / "bhudrishti.db"
DB_PATH.parent.mkdir(parents=True, exist_ok=True)


def _conn():
    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row
    return c


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
        self.db_path = DB_PATH
        self._init_db()

    def _init_db(self):
        with _conn() as c:
            c.execute("""CREATE TABLE IF NOT EXISTS extractions (
                extraction_id TEXT PRIMARY KEY, source_filename TEXT NOT NULL,
                geometry_wkt TEXT NOT NULL, image_width INTEGER, image_height INTEGER,
                image_format TEXT, confidence_heuristic REAL, pixel_polygon_json TEXT,
                inference_mode TEXT, notes TEXT, parcel_candidates_json TEXT,
                roof_footprints_json TEXT, created_at TEXT, status TEXT, is_demo_data INTEGER,
                dataset_id TEXT
            )""")
            c.commit()

    def new_id(self) -> str:
        with _conn() as c:
            row = c.execute("SELECT extraction_id FROM extractions ORDER BY CAST(substr(extraction_id,5) AS INTEGER) DESC LIMIT 1").fetchone()
        n = int(row[0][4:]) + 1 if row else 1
        return f"EXT-{n:04d}"

    def save(self, record: ExtractionRecord) -> ExtractionRecord:
        with _conn() as c:
            c.execute("""INSERT OR REPLACE INTO extractions VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", (
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
        with _conn() as c: return [self._row(r) for r in c.execute("SELECT * FROM extractions ORDER BY CAST(substr(extraction_id,5) AS INTEGER)").fetchall()]

    def update_status(self, extraction_id: str, status: str):
        with _conn() as c: c.execute("UPDATE extractions SET status=? WHERE extraction_id=?", (status, extraction_id))


ExtractionStore = PersistentExtractionRepository
extraction_store = PersistentExtractionRepository()
