from __future__ import annotations

from typing import Any

from src.connectors.base import DatabaseConnector
from src.connectors.common import apply_key_flags, new_column, new_object
from src.connectors.object_metadata import normalize_object_metadata

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
        """Discover SQL Server tables, views, and triggers."""

        schema_filter = self.config.get("schema_name")

        query = """
            SELECT
                TABLE_SCHEMA,
                TABLE_NAME,
                TABLE_TYPE
            FROM INFORMATION_SCHEMA.TABLES
            WHERE TABLE_TYPE IN (
                'BASE TABLE',
                'VIEW'
            )
        """

        parameters: list[Any] = []

        if schema_filter:
            query += " AND TABLE_SCHEMA = ?"
            parameters.append(schema_filter)

        query += """
            ORDER BY
                TABLE_SCHEMA,
                TABLE_NAME
        """

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

            object_type = (
                "TABLE"
                if table_type == "BASE TABLE"
                else "VIEW"
            )

            object_ddl = None

            if object_type == "VIEW":
                object_ddl = self._get_module_definition(
                    schema_name=schema_name,
                    object_name=object_name,
                )

            item = new_object(
                schema_name=schema_name,
                object_name=object_name,
                object_type=object_type,
                object_ddl=object_ddl,
                metadata={
                    "source_table_type": table_type,
                    "language": (
                        "TSQL"
                        if object_type == "VIEW"
                        else None
                    ),
                    "materialized": False,
                    "enabled": True,
                },
            )

            item["columns"] = self._columns(
                schema_name,
                object_name,
            )

            if object_type == "TABLE":
                item["primary_key_columns"] = (
                    self._primary_keys(
                        schema_name,
                        object_name,
                    )
                )

                item["foreign_keys"] = (
                    self._foreign_keys(
                        schema_name,
                        object_name,
                    )
                )

                apply_key_flags(item)

            item["object_metadata"] = (
                normalize_object_metadata(
                    metadata=item.get(
                        "object_metadata"
                    ),
                    object_ddl=item.get(
                        "object_ddl"
                    ),
                    object_type=object_type,
                    column_count=len(
                        item.get("columns", [])
                    ),
                    foreign_key_count=len(
                        item.get("foreign_keys", [])
                    ),
                )
            )

            objects.append(item)

        objects.extend(
            self._discover_triggers(
                schema_filter=schema_filter,
            )
        )

        return objects

    def _discover_triggers(
        self,
        schema_filter: str | None = None,
    ) -> list[dict[str, Any]]:
        """Discover table-level SQL Server DML triggers."""

        query = """
            SELECT
                trigger_info.object_id,
                trigger_schema.name AS trigger_schema,
                trigger_info.name AS trigger_name,
                table_schema.name AS table_schema,
                table_info.name AS table_name,
                module_info.definition AS trigger_ddl,
                trigger_info.is_disabled,
                trigger_info.is_instead_of_trigger,
                trigger_object.create_date,
                trigger_object.modify_date
            FROM sys.triggers AS trigger_info

            JOIN sys.objects AS trigger_object
              ON trigger_object.object_id =
                 trigger_info.object_id

            JOIN sys.schemas AS trigger_schema
              ON trigger_schema.schema_id =
                 trigger_object.schema_id

            JOIN sys.tables AS table_info
              ON table_info.object_id =
                 trigger_info.parent_id

            JOIN sys.schemas AS table_schema
              ON table_schema.schema_id =
                 table_info.schema_id

            LEFT JOIN sys.sql_modules AS module_info
              ON module_info.object_id =
                 trigger_info.object_id

            WHERE trigger_info.parent_class = 1
        """

        parameters: list[Any] = []

        if schema_filter:
            query += """
              AND table_schema.name = ?
            """
            parameters.append(schema_filter)

        query += """
            ORDER BY
                trigger_schema.name,
                trigger_info.name
        """

        cursor = self.connection.cursor()

        try:
            if parameters:
                cursor.execute(query, *parameters)
            else:
                cursor.execute(query)

            rows = cursor.fetchall()
        finally:
            cursor.close()

        triggers: list[dict[str, Any]] = []

        for row in rows:
            trigger_object_id = int(row[0])
            trigger_schema = str(row[1])
            trigger_name = str(row[2])
            table_schema = str(row[3])
            table_name = str(row[4])

            trigger_ddl = (
                str(row[5])
                if row[5] is not None
                else None
            )

            is_disabled = bool(row[6])
            is_instead_of = bool(row[7])
            created_at = row[8]
            modified_at = row[9]

            trigger_events = self._trigger_events(
                trigger_object_id
            )

            trigger_timing = (
                "INSTEAD OF"
                if is_instead_of
                else "AFTER"
            )

            trigger = new_object(
                schema_name=trigger_schema,
                object_name=trigger_name,
                object_type="TRIGGER",
                object_ddl=trigger_ddl,
                metadata={
                    "language": "TSQL",
                    "parameter_count": 0,
                    "created_at": created_at,
                    "last_altered_at": modified_at,
                    "return_type": None,
                    "materialized": False,
                    "enabled": not is_disabled,
                    "is_disabled": is_disabled,
                    "instead_of": is_instead_of,
                    "trigger_table_schema": table_schema,
                    "trigger_table": table_name,
                    "trigger_timing": trigger_timing,
                    "trigger_events": trigger_events,
                    "orientation": "STATEMENT",
                },
            )

            triggers.append(trigger)

        return triggers
    
    def _trigger_events(
        self,
        trigger_object_id: int,
    ) -> list:
        """Return INSERT, UPDATE, or DELETE events for a trigger."""

        query = """
            SELECT type_desc
            FROM sys.trigger_events
            WHERE object_id = ?
            ORDER BY type_desc
        """

        cursor = self.connection.cursor()

        try:
            cursor.execute(
                query,
                trigger_object_id,
            )

            rows = cursor.fetchall()
        finally:
            cursor.close()

        events: list[str] = []

        for row in rows:
            event_name = str(row[0]).strip().upper()

            if event_name and event_name not in events:
                events.append(event_name)

        return events
    
    def _get_module_definition(
        self,
        schema_name: str,
        object_name: str,
    ) -> str | None:
        """Return the SQL definition for a SQL Server module."""

        query = """
            SELECT module_info.definition
            FROM sys.sql_modules AS module_info

            JOIN sys.objects AS object_info
              ON object_info.object_id =
                 module_info.object_id

            JOIN sys.schemas AS schema_info
              ON schema_info.schema_id =
                 object_info.schema_id

            WHERE schema_info.name = ?
              AND object_info.name = ?
        """

        cursor = self.connection.cursor()

        try:
            cursor.execute(
                query,
                schema_name,
                object_name,
            )

            row = cursor.fetchone()
        finally:
            cursor.close()

        if row is None or row[0] is None:
            return None

        return str(row[0])

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
