"""Lightweight persistence abstractions for the BhuDrishti prototype.

The current implementation intentionally remains in-memory for the SIH demo.
API code depends on small repository contracts so the storage layer can later
be replaced by SQLite/PostgreSQL/PostGIS without rewriting the API workflows.
"""
from __future__ import annotations
from typing import Protocol, TypeVar, Generic

T = TypeVar("T")

class Repository(Protocol, Generic[T]):
    def get(self, key: str) -> T | None: ...
    def save(self, value: T) -> T: ...
    def all(self) -> list[T]: ...

class InMemoryRepository(Generic[T]):
<<<<<<< HEAD
    """Legacy generic helper retained for compatibility; workflow stores use SQLite."""
=======
    """Generic in-memory repository used by the prototype runtime."""
>>>>>>> origin/main
    def __init__(self):
        self._items: dict[str, T] = {}

    def get(self, key: str) -> T | None:
        return self._items.get(key)

    def save(self, value: T, key: str | None = None) -> T:
        if key is None:
            key = getattr(value, "extraction_id", None) or getattr(value, "parcel_id", None)
        if not key:
            raise ValueError("Repository item needs extraction_id or parcel_id")
        self._items[key] = value
        return value

    def all(self) -> list[T]:
        return list(self._items.values())

<<<<<<< HEAD
PERSISTENCE_MODE = "sqlite_file"
PERSISTENCE_LABEL = "SQLite File / Prototype Persistence"
=======
PERSISTENCE_MODE = "in_memory_session"
PERSISTENCE_LABEL = "Session Memory / Prototype"
>>>>>>> origin/main
