from __future__ import annotations

from dataclasses import dataclass
from time import perf_counter
from typing import Any

import psycopg
from psycopg import Connection

from src.models.enums import DatabaseType


@dataclass
class ConnectionTestResult:
    success: bool
    message: str
    response_time_ms: int | None = None


def build_postgresql_connection(
    safe_config: dict[str, Any],
    password: str,
) -> Connection:
    connection = psycopg.connect(
        host=safe_config["host"],
        port=safe_config["port"],
        dbname=safe_config["database_name"],
        user=safe_config["username"],
        password=password,
        sslmode=(
            "require"
            if safe_config.get("ssl_enabled", True)
            else "prefer"
        ),
        connect_timeout=10,
    )

    connection.execute(
        "SET SESSION CHARACTERISTICS AS TRANSACTION READ ONLY"
    )

    return connection


def test_connection(
    database_type: DatabaseType,
    safe_config: dict[str, Any],
    password: str,
) -> ConnectionTestResult:
    if database_type != DatabaseType.POSTGRESQL:
        return ConnectionTestResult(
            success=False,
            message=(
                f"Connection adapter is not yet available "
                f"for {database_type.value}"
            ),
        )

    started_at = perf_counter()
    connection: Connection | None = None

    try:
        connection = build_postgresql_connection(
            safe_config=safe_config,
            password=password,
        )

        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()

        elapsed_ms = round(
            (perf_counter() - started_at) * 1000
        )

        return ConnectionTestResult(
            success=True,
            message="Connection successful",
            response_time_ms=elapsed_ms,
        )

    except psycopg.Error:
        return ConnectionTestResult(
            success=False,
            message=(
                "Unable to connect to the source PostgreSQL "
                "database using the provided details"
            ),
        )

    finally:
        if connection is not None:
            connection.close()