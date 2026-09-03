from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from time import perf_counter
from typing import Any


@dataclass(frozen=True)
class ConnectionTestResult:
    success: bool
    message: str
    response_time_ms: int | None = None
    error_code: str | None = None


class DatabaseConnector(ABC):
    """Common interface for every supported source-database connector."""

    def __init__(
        self,
        config: dict[str, Any],
        password: str,
    ):
        self.config = config
        self.password = password
        self.connection: Any = None

    @property
    @abstractmethod
    def health_query(self) -> str:
        """Return a vendor-specific connection health query."""

    @abstractmethod
    def connect(self) -> Any:
        """Open and return the source-database connection."""

    @abstractmethod
    def make_read_only(self) -> None:
        """Configure the open connection for read-only Discovery."""

    @abstractmethod
    def execute_one(self, query: str) -> Any:
        """Execute a small read query and return one row."""

    @abstractmethod
    def discover_metadata(
        self,
    ) -> list[dict[str, Any]]:
        """Return metadata using the shared Discovery format."""

    def test_connection(self) -> ConnectionTestResult:
        started_at = perf_counter()

        try:
            self.connect()
            self.make_read_only()
            self.execute_one(self.health_query)

            elapsed_ms = round(
                (perf_counter() - started_at) * 1000
            )

            return ConnectionTestResult(
                success=True,
                message="Connection successful",
                response_time_ms=elapsed_ms,
            )

        except ModuleNotFoundError:
            return ConnectionTestResult(
                success=False,
                message=(
                    "The required database driver is not "
                    "installed."
                ),
                error_code="DATABASE_DRIVER_NOT_INSTALLED",
            )

        except Exception as error:
            return ConnectionTestResult(
                success=False,
                message=(
                    "Datasource connection failed. "
                    f"Failure type: "
                    f"{error.__class__.__name__}."
                ),
                error_code="CONNECTION_FAILED",
            )

        finally:
            self.close()

    def close(self) -> None:
        try:
            if self.connection is not None:
                self.connection.close()
        finally:
            self.connection = None
            self.password = ""

    def __enter__(self) -> DatabaseConnector:
        try:
            self.connect()
            self.make_read_only()
            return self

        except Exception:
            self.close()
            raise

    def __exit__(
        self,
        exc_type,
        exc_value,
        traceback,
    ) -> bool:
        self.close()
        return False
