from __future__ import annotations

from dataclasses import dataclass
from time import perf_counter
from typing import Any

from src.connectors.factory import create_connector
from src.models.enums import DatabaseType


@dataclass
class ConnectionTestResult:
    success: bool
    message: str
    response_time_ms: int | None = None
    error_code: str | None = None


def test_connection(
    database_type: DatabaseType,
    safe_config: dict[str, Any],
    password: str,
) -> ConnectionTestResult:
    """Test connectivity and verify the selected schema when supplied."""
    connector = None
    started_at = perf_counter()

    try:
        connector = create_connector(
            database_type=database_type,
            config=safe_config,
            password=password,
        )
        connector.connect()
        connector.make_read_only()
        connector.execute_one(connector.health_query)

        schema_name = safe_config.get("schema_name")
        if schema_name and not _schema_exists(
            connector=connector,
            database_type=database_type,
            schema_name=str(schema_name),
        ):
            elapsed_ms = round(
                (perf_counter() - started_at) * 1000
            )
            return ConnectionTestResult(
                success=False,
                message=(
                    f"Schema '{schema_name}' does not exist "
                    "or is not accessible."
                ),
                response_time_ms=elapsed_ms,
                error_code="SCHEMA_NOT_FOUND",
            )

        elapsed_ms = round(
            (perf_counter() - started_at) * 1000
        )
        return ConnectionTestResult(
            success=True,
            message="Connection and schema validation successful",
            response_time_ms=elapsed_ms,
        )

    except ModuleNotFoundError as error:
        return ConnectionTestResult(
            success=False,
            message=(
                "The required database driver is not installed: "
                f"{error.name}"
            ),
            error_code="DATABASE_DRIVER_NOT_INSTALLED",
        )

    except ValueError:
        return ConnectionTestResult(
            success=False,
            message=f"Unsupported database type: {database_type}",
            error_code="UNSUPPORTED_DATABASE_TYPE",
        )

    except Exception as error:
        return ConnectionTestResult(
            success=False,
            message=(
                "Datasource connection failed. "
                f"Failure type: {error.__class__.__name__}."
            ),
            error_code="CONNECTION_FAILED",
        )

    finally:
        if connector is not None:
            connector.close()


def _schema_exists(
    connector,
    database_type: DatabaseType,
    schema_name: str,
) -> bool:
    """Return whether an exact, accessible schema match exists."""
    database_value = (
        database_type.value
        if hasattr(database_type, "value")
        else str(database_type)
    )
    database_value = database_value.upper()
    cursor = connector.connection.cursor()

    try:
        if database_value == "POSTGRESQL":
            cursor.execute(
                """
                SELECT EXISTS (
                    SELECT 1
                    FROM information_schema.schemata
                    WHERE schema_name = %s
                )
                """,
                (schema_name,),
            )

        elif database_value == "MYSQL":
            cursor.execute(
                """
                SELECT EXISTS (
                    SELECT 1
                    FROM information_schema.SCHEMATA
                    WHERE SCHEMA_NAME = %s
                )
                """,
                (schema_name,),
            )

        elif database_value == "SQL_SERVER":
            cursor.execute(
                """
                SELECT CASE WHEN EXISTS (
                    SELECT 1
                    FROM sys.schemas
                    WHERE name = ?
                ) THEN 1 ELSE 0 END
                """,
                schema_name,
            )

        elif database_value == "ORACLE":
            cursor.execute(
                """
                SELECT CASE WHEN EXISTS (
                    SELECT 1
                    FROM ALL_USERS
                    WHERE USERNAME = :schema_name
                ) THEN 1 ELSE 0 END
                FROM DUAL
                """,
                schema_name=schema_name.upper(),
            )

        else:
            raise ValueError(
                f"Unsupported database type: {database_value}"
            )

        row = cursor.fetchone()
        return bool(row and row[0])

    finally:
        cursor.close()


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
    try:
        connector.connect()
        connector.make_read_only()
        return connector
    except Exception:
        connector.close()
        raise
