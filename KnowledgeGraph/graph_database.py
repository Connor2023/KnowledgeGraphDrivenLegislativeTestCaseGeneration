from abc import ABC, abstractmethod
from typing import Any, Sequence


class DatabaseAPI(ABC):
    """Storage backend for the knowledge graph.

    The tuple-ingestion methods (:meth:`fetch_edges`, :meth:`upsert_edges`,
    :meth:`augment_edges`) are batch-oriented on purpose: a round trip to Aura
    costs far more than the query itself, so the unit of work is a list of rows
    rather than a single edge.
    """

    def __init__(self):
        pass

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.shutdown()

    @abstractmethod
    def start(self):
        pass

    @abstractmethod
    def shutdown(self):
        pass

    @abstractmethod
    def clear(self):
        pass

    @abstractmethod
    def ensure_schema(self, base_label: str = "Entity") -> None:
        """Create whatever indexes/constraints the ingestion path needs."""

    @abstractmethod
    def fetch_edges(
        self, keys: Sequence[tuple[str, str, str]], **kwargs
    ) -> dict[tuple[str, str, str], dict[str, Any]]:
        """Return current state for each ``(from, relationship, to)`` key that exists."""

    @abstractmethod
    def upsert_edges(self, rows: Sequence[dict[str, Any]], **kwargs) -> dict[str, int]:
        """Write pre-computed edge properties for a batch of tuples."""

    @abstractmethod
    def augment_edges(
        self, rows: Sequence[dict[str, Any]], *, first_expression: str,
        update_expression: str, **kwargs
    ) -> dict[str, int]:
        """Apply an augmentation rule inside the database itself."""
