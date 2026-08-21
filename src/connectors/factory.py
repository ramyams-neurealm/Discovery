from __future__ import annotations

from typing import Any

from src.connectors.base import DatabaseConnector
from src.models.enums import DatabaseType


def create_connector(
    database_type: DatabaseType | str,
    config: dict[str, Any],
    password: str,
) -> DatabaseConnector:
    db_type = (
        database_type
        if isinstance(database_type, DatabaseType)
        else DatabaseType(database_type)
    )

    if db_type == DatabaseType.POSTGRESQL:
        from src.connectors.postgresql import PostgreSQLConnector
        return PostgreSQLConnector(config, password)

    if db_type == DatabaseType.MYSQL:
        from src.connectors.mysql import MySQLConnector
        return MySQLConnector(config, password)

    if db_type == DatabaseType.SQL_SERVER:
        from src.connectors.sql_server import SQLServerConnector
        return SQLServerConnector(config, password)

    if db_type == DatabaseType.ORACLE:
        from src.connectors.oracle import OracleConnector
        return OracleConnector(config, password)

    raise ValueError(f"Unsupported database type: {db_type}")
