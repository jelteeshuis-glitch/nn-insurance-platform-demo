"""
Persistence Layer — Abstract Repository Pattern

Provides a storage-agnostic repository interface plus a concrete in-memory
implementation used by every bounded context. Services depend only on the
abstract :class:`Repository` interface (dependency inversion), so the backing
store can be swapped for a real database without touching business logic.

Per ADR-005 (Security-First Design) a production deployment would back these
repositories with SQLAlchemy using parameterized queries (never string
interpolation — contrast ``legacy/src/database.py`` which is riddled with SQL
injection). The in-memory implementation keeps the demo self-contained while
preserving the exact async interface a SQLAlchemy repository would expose.
"""
from abc import ABC, abstractmethod
from typing import Callable, Generic, Optional, TypeVar

T = TypeVar("T")


class Repository(ABC, Generic[T]):
    """Abstract, async repository interface for aggregate roots."""

    @abstractmethod
    async def save(self, entity: T) -> T:
        """Persist (insert or update) an entity and return it."""

    @abstractmethod
    async def get(self, entity_id: str) -> Optional[T]:
        """Fetch an entity by its identity, or ``None`` if absent."""

    @abstractmethod
    async def list_all(self) -> list[T]:
        """Return all entities (a real store would paginate)."""

    @abstractmethod
    async def delete(self, entity_id: str) -> bool:
        """Remove an entity. Returns ``True`` if something was deleted."""

    @abstractmethod
    async def exists(self, entity_id: str) -> bool:
        """Return ``True`` if an entity with the given id exists."""


class InMemoryRepository(Repository[T]):
    """Thread-unsafe in-memory repository — suitable for tests and the demo.

    Identity is extracted via ``id_getter`` (defaults to ``entity.id``) so the
    same implementation works for both Pydantic models and dataclasses.
    """

    def __init__(self, id_getter: Optional[Callable[[T], str]] = None):
        self._store: dict[str, T] = {}
        self._id_getter: Callable[[T], str] = id_getter or (lambda e: e.id)

    def _key(self, entity: T) -> str:
        return str(self._id_getter(entity))

    async def save(self, entity: T) -> T:
        self._store[self._key(entity)] = entity
        return entity

    async def get(self, entity_id: str) -> Optional[T]:
        return self._store.get(str(entity_id))

    async def list_all(self) -> list[T]:
        return list(self._store.values())

    async def delete(self, entity_id: str) -> bool:
        return self._store.pop(str(entity_id), None) is not None

    async def exists(self, entity_id: str) -> bool:
        return str(entity_id) in self._store

    async def find(self, predicate: Callable[[T], bool]) -> list[T]:
        """Return all entities matching ``predicate`` (in-memory query helper)."""
        return [e for e in self._store.values() if predicate(e)]
