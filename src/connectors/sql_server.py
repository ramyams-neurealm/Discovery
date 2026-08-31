from __future__ import annotations

from typing import Any

from src.connectors.base import DatabaseConnector
from src.connectors.common import apply_key_flags, new_column, new_object


class SQLServerConnector(DatabaseConnector):
    """SQL Server connector supporting modern and legacy ODBC drivers."""

    DRIVER_PREFERENCE = (
        "ODBC Driver 18 for SQL Server",
        "ODBC Driver 17 for SQL Server",
        "SQL Server",
    )

    MODERN_DRIVERS = {
        "ODBC Driver 18 for SQL Server",
        "ODBC Driver 17 for SQL Server",
    }

    @property
    def health_query(self) -> str:
        return "SELECT 1"

    def connect(self):
        import pyodbc

        available_drivers = list(pyodbc.drivers())
        driver = self._select_driver(available_drivers)
        server = self._server_address()

        connection_parts = [
            f"DRIVER={{{driver}}}",
            f"SERVER={server}",
            f"DATABASE={self.config['database_name']}",
            f"UID={self.config['username']}",
            f"PWD={self.password}",
            "APP=Agentic Discovery",
            "Connection Timeout=10",
        ]

        if driver in self.MODERN_DRIVERS:
            ssl_enabled = bool(self.config.get("ssl_enabled", True))
            connection_parts.extend(
                [
                    "Encrypt=yes" if ssl_enabled else "Encrypt=no",
                    "TrustServerCertificate=yes",
                ]
            )

        connection_string = ";".join(connection_parts) + ";"

        try:
            self.connection = pyodbc.connect(
                connection_string,
                autocommit=False,
                timeout=10,
            )
        except pyodbc.Error as error:
            raise ConnectionError(
                "SQL Server connection failed. "
                f"Driver: {driver}. "
                f"Server: {server}. "
                f"Failure type: {error.__class__.__name__}. "
                f"Driver message: {error}"
            ) from error

        return self.connection

    def _select_driver(self, available_drivers: list[str]) -> str:
        configured_driver = str(
            self.config.get("odbc_driver") or ""
        ).strip()

        candidates: list[str] = []
        if configured_driver:
            candidates.append(configured_driver)

        for driver in self.DRIVER_PREFERENCE:
            if driver not in candidates:
                candidates.append(driver)

        for candidate in candidates:
            if candidate in available_drivers:
                return candidate

        raise RuntimeError(
            "No compatible SQL Server ODBC driver is installed. "
            f"Available drivers: {available_drivers}"
        )

    def _server_address(self) -> str:
        host = str(self.config["host"]).strip()
        if not host:
            raise ValueError("SQL Server host must not be blank")

        if "\\" in host or "," in host:
            return host

        port = int(self.config.get("port", 1433))
        return f"{host},{port}"

    def make_read_only(self) -> None:
        """Read-only access must be enforced by SQL Server permissions."""
        return None

    def execute_one(self, query: str) -> Any:
        cursor = self.connection.cursor()
        try:
            cursor.execute(query)
            return cursor.fetchone()
        finally:
            cursor.close()

    def discover_metadata(self) -> list[dict[str, Any]]:
        """Discover tables and views with columns and key metadata."""
        schema_filter = self.config.get("schema_name")
        query = """
            SELECT TABLE_SCHEMA, TABLE_NAME, TABLE_TYPE
            FROM INFORMATION_SCHEMA.TABLES
            WHERE TABLE_TYPE IN ('BASE TABLE', 'VIEW')
        """
        parameters: list[Any] = []

        if schema_filter:
            query += " AND TABLE_SCHEMA = ?"
            parameters.append(schema_filter)

        query += " ORDER BY TABLE_SCHEMA, TABLE_NAME"

        cursor = self.connection.cursor()
        try:
            if parameters:
                cursor.execute(query, *parameters)
            else:
                cursor.execute(query)
            rows = cursor.fetchall()
        finally:
            cursor.close()

        objects: list[dict[str, Any]] = []
        for row in rows:
            schema_name = str(row[0])
            object_name = str(row[1])
            table_type = str(row[2])
            object_type = "TABLE" if table_type == "BASE TABLE" else "VIEW"

            item = new_object(
                schema_name,
                object_name,
                object_type,
                metadata={"source_table_type": table_type},
            )
            item["columns"] = self._columns(schema_name, object_name)

            if object_type == "TABLE":
                item["primary_key_columns"] = self._primary_keys(
                    schema_name,
                    object_name,
                )
                item["foreign_keys"] = self._foreign_keys(
                    schema_name,
                    object_name,
                )
                apply_key_flags(item)

            objects.append(item)

        return objects

    def _columns(
        self,
        schema_name: str,
        object_name: str,
    ) -> list[dict[str, Any]]:
        query = """
            SELECT COLUMN_NAME, ORDINAL_POSITION, DATA_TYPE, IS_NULLABLE,
                   COLUMN_DEFAULT, CHARACTER_MAXIMUM_LENGTH
            FROM INFORMATION_SCHEMA.COLUMNS
            WHERE TABLE_SCHEMA = ? AND TABLE_NAME = ?
            ORDER BY ORDINAL_POSITION
        """

        cursor = self.connection.cursor()
        try:
            cursor.execute(query, schema_name, object_name)
            rows = cursor.fetchall()
        finally:
            cursor.close()

        results: list[dict[str, Any]] = []
        length_types = {
            "VARCHAR",
            "NVARCHAR",
            "CHAR",
            "NCHAR",
            "BINARY",
            "VARBINARY",
        }

        for row in rows:
            column_name = str(row[0])
            ordinal_position = int(row[1])
            native_data_type = str(row[2])
            data_type = native_data_type.upper()
            nullable = str(row[3]).upper() == "YES"
            default_value = row[4]
            maximum_length = row[5]

            if maximum_length is not None and data_type in length_types:
                length = int(maximum_length)
                data_type = (
                    f"{data_type}(MAX)"
                    if length == -1
                    else f"{data_type}({length})"
                )

            results.append(
                new_column(
                    column_name,
                    ordinal_position,
                    data_type,
                    nullable,
                    default_value,
                    native_data_type,
                )
            )

        return results

    def _primary_keys(
        self,
        schema_name: str,
        table_name: str,
    ) -> list[str]:
        query = """
            SELECT kcu.COLUMN_NAME
            FROM INFORMATION_SCHEMA.TABLE_CONSTRAINTS AS tc
            JOIN INFORMATION_SCHEMA.KEY_COLUMN_USAGE AS kcu
              ON tc.CONSTRAINT_NAME = kcu.CONSTRAINT_NAME
             AND tc.CONSTRAINT_SCHEMA = kcu.CONSTRAINT_SCHEMA
             AND tc.TABLE_SCHEMA = kcu.TABLE_SCHEMA
             AND tc.TABLE_NAME = kcu.TABLE_NAME
            WHERE tc.CONSTRAINT_TYPE = 'PRIMARY KEY'
              AND tc.TABLE_SCHEMA = ?
              AND tc.TABLE_NAME = ?
            ORDER BY kcu.ORDINAL_POSITION
        """

        cursor = self.connection.cursor()
        try:
            cursor.execute(query, schema_name, table_name)
            return [str(row[0]) for row in cursor.fetchall()]
        finally:
            cursor.close()

    def _foreign_keys(
        self,
        schema_name: str,
        table_name: str,
    ) -> list[dict[str, Any]]:
        query = """
            SELECT fk.name, pc.name, rs.name, rt.name, rc.name
            FROM sys.foreign_keys AS fk
            JOIN sys.foreign_key_columns AS fkc
              ON fk.object_id = fkc.constraint_object_id
            JOIN sys.tables AS pt
              ON fkc.parent_object_id = pt.object_id
            JOIN sys.schemas AS ps
              ON pt.schema_id = ps.schema_id
            JOIN sys.columns AS pc
              ON pc.object_id = pt.object_id
             AND pc.column_id = fkc.parent_column_id
            JOIN sys.tables AS rt
              ON fkc.referenced_object_id = rt.object_id
            JOIN sys.schemas AS rs
              ON rt.schema_id = rs.schema_id
            JOIN sys.columns AS rc
              ON rc.object_id = rt.object_id
             AND rc.column_id = fkc.referenced_column_id
            WHERE ps.name = ? AND pt.name = ?
            ORDER BY fk.name, fkc.constraint_column_id
        """

        cursor = self.connection.cursor()
        try:
            cursor.execute(query, schema_name, table_name)
            rows = cursor.fetchall()
        finally:
            cursor.close()

        return [
            {
                "constraint_name": str(row[0]),
                "source_schema": schema_name,
                "source_table": table_name,
                "source_column": str(row[1]),
                "target_schema": str(row[2]),
                "target_table": str(row[3]),
                "target_column": str(row[4]),
            }
            for row in rows
        ]
