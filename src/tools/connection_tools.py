from dataclasses import dataclass
from src.models.enums import DatabaseType


@dataclass
class ConnectionTestResult:
    success: bool
    message: str
    response_time_ms: int | None = None


def test_connection(database_type: DatabaseType, safe_config: dict, password: str) -> ConnectionTestResult:
    # Implement vendor adapters here. Do not include the password in logs or errors.
    # PostgreSQL: psycopg; MySQL: mysql connector; SQL Server: pyodbc; Oracle: oracledb.
    raise NotImplementedError(f"Connection adapter not implemented for {database_type}")
