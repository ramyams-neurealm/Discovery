from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from time import perf_counter
from typing import Any


@dataclass
class ConnectionTestResult:
    success: bool
    message: str
    response_time_ms: int | None = None


class DatabaseConnector(ABC):
    """Common interface implemented by every source-database connector."""

    def __init__(self, config: dict[str, Any], password: str):
        self.config = config
        self.password = password
        self.connection: Any = None

    @abstractmethod
    def connect(self) -> Any:
        """Open and return a source-database connection."""

    @abstractmethod
    def make_read_only(self) -> None:
        """Configure the open connection for read-only discovery where supported."""

    @abstractmethod
    def execute_one(self, query: str) -> Any:
        """Execute a small query and return one row."""

    @abstractmethod
    def discover_metadata(self) -> list[dict[str, Any]]:
        """Return objects and columns in the shared discovery format."""

    def test_connection(self) -> ConnectionTestResult:
        started = perf_counter()
        try:
            self.connect()
            self.make_read_only()
            self.execute_one(self.health_query)
            elapsed = round((perf_counter() - started) * 1000)
            return ConnectionTestResult(True, "Connection successful", elapsed)
        except Exception as error:
            return ConnectionTestResult(
                False,
                f"Connection failed: {error.__class__.__name__}",
                None,
            )
        finally:
            self.close()

    @property
    @abstractmethod
    def health_query(self) -> str:
        """Return a vendor-appropriate health query."""

    def close(self) -> None:
        if self.connection is not None:
            try:
                self.connection.close()
            finally:
                self.connection = None

    def __enter__(self):
        self.connect()
        self.make_read_only()
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.close()
        return False
