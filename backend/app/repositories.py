"""Repository metadata; authoritative stores use the shared DB adapter."""
from typing import Protocol, TypeVar, Generic
from .persistence import PERSISTENCE_MODE, PERSISTENCE_LABEL
T = TypeVar("T")

class Repository(Protocol, Generic[T]):
    def get(self, key: str) -> T | None: ...
    def save(self, value: T) -> T: ...
    def all(self) -> list[T]: ...

class InMemoryRepository(Generic[T]):
    """Legacy helper for non-authoritative tests only; not used by API stores."""
    def __init__(self): self._items: dict[str, T] = {}
    def get(self, key: str) -> T | None: return self._items.get(key)
    def save(self, value: T, key: str | None = None) -> T:
        if key is None: key = getattr(value, "extraction_id", None) or getattr(value, "parcel_id", None)
        if not key: raise ValueError("Repository item needs extraction_id or parcel_id")
        self._items[key] = value
        return value
    def all(self) -> list[T]: return list(self._items.values())
