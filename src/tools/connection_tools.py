from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from src.connectors.factory import create_connector
from src.models.enums import DatabaseType


@dataclass
class ConnectionTestResult:
    success: bool
    message: str
    response_time_ms: int | None = None


def test_connection(
    database_type: DatabaseType,
    safe_config: dict[str, Any],
    password: str,
) -> ConnectionTestResult:
    """Test any supported datasource through the connector factory."""
    try:
        connector = create_connector(
            database_type=database_type,
            config=safe_config,
            password=password,
        )
        result = connector.test_connection()
        return ConnectionTestResult(
            success=result.success,
            message=result.message,
            response_time_ms=result.response_time_ms,
        )
    except ModuleNotFoundError as error:
        return ConnectionTestResult(
            success=False,
            message=(
                "The required database driver is not installed: "
                f"{error.name}"
            ),
        )
    except ValueError:
        return ConnectionTestResult(
            success=False,
            message=f"Unsupported database type: {database_type}",
        )


def open_source_connector(
    database_type: DatabaseType | str,
    safe_config: dict[str, Any],
    password: str,
):
    """Create, connect, and configure the selected datasource connector."""
    connector = create_connector(
        database_type=database_type,
        config=safe_config,
        password=password,
    )
    connector.connect()
    connector.make_read_only()
    return connector
