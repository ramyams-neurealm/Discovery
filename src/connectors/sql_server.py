from __future__ import annotations

from typing import Any

from src.connectors.base import DatabaseConnector
from src.connectors.common import apply_key_flags, new_column, new_object


class SQLServerConnector(DatabaseConnector):
    @property
    def health_query(self) -> str:
        return "SELECT 1"

    def connect(self):
        import pyodbc

        driver = self.config.get("odbc_driver", "ODBC Driver 18 for SQL Server")
        encrypt = "yes" if self.config.get("ssl_enabled", True) else "no"
        connection_string = (
            f"DRIVER={{{driver}}};"
            f"SERVER={self.config['host']},{int(self.config.get('port', 1433))};"
            f"DATABASE={self.config['database_name']};"
            f"UID={self.config['username']};PWD={self.password};"
            f"Encrypt={encrypt};TrustServerCertificate=yes;"
            "Connection Timeout=10;"
        )
        self.connection = pyodbc.connect(connection_string, autocommit=False)
        return self.connection

    def make_read_only(self) -> None:
        return None

    def execute_one(self, query: str) -> Any:
        cursor = self.connection.cursor()
        try:
            cursor.execute(query)
            return cursor.fetchone()
        finally:
            cursor.close()

    def discover_metadata(self) -> list[dict[str, Any]]:
        schema_filter = self.config.get("schema_name")
        query = """
            SELECT TABLE_SCHEMA, TABLE_NAME, TABLE_TYPE
            FROM INFORMATION_SCHEMA.TABLES
            WHERE TABLE_TYPE IN ('BASE TABLE', 'VIEW')
        """
        params = []
        if schema_filter:
            query += " AND TABLE_SCHEMA = ?"
            params.append(schema_filter)
        query += " ORDER BY TABLE_SCHEMA, TABLE_NAME"
        cursor = self.connection.cursor()
        try:
            cursor.execute(query, params)
            rows = cursor.fetchall()
        finally:
            cursor.close()

        objects = []
        for row in rows:
            schema_name, object_name, table_type = row
            object_type = "TABLE" if table_type == "BASE TABLE" else "VIEW"
            item = new_object(schema_name, object_name, object_type)
            item["columns"] = self._columns(schema_name, object_name)
            if object_type == "TABLE":
                item["primary_key_columns"] = self._primary_keys(schema_name, object_name)
                item["foreign_keys"] = self._foreign_keys(schema_name, object_name)
                apply_key_flags(item)
            objects.append(item)
        return objects

    def _columns(self, schema_name: str, object_name: str):
        query = """
            SELECT COLUMN_NAME, ORDINAL_POSITION, DATA_TYPE, IS_NULLABLE,
                   COLUMN_DEFAULT, CHARACTER_MAXIMUM_LENGTH
            FROM INFORMATION_SCHEMA.COLUMNS
            WHERE TABLE_SCHEMA = ? AND TABLE_NAME = ?
            ORDER BY ORDINAL_POSITION
        """
        cursor = self.connection.cursor()
        try:
            cursor.execute(query, (schema_name, object_name))
            rows = cursor.fetchall()
        finally:
            cursor.close()
        result = []
        for row in rows:
            data_type = str(row[2]).upper()
            if row[5] and data_type in {"VARCHAR", "NVARCHAR", "CHAR", "NCHAR"}:
                data_type = f"{data_type}({row[5]})"
            result.append(new_column(row[0], row[1], data_type, row[3] == "YES", row[4], row[2]))
        return result

    def _primary_keys(self, schema_name: str, table_name: str):
        query = """
            SELECT kcu.COLUMN_NAME
            FROM INFORMATION_SCHEMA.TABLE_CONSTRAINTS tc
            JOIN INFORMATION_SCHEMA.KEY_COLUMN_USAGE kcu
              ON tc.CONSTRAINT_NAME = kcu.CONSTRAINT_NAME
             AND tc.CONSTRAINT_SCHEMA = kcu.CONSTRAINT_SCHEMA
            WHERE tc.CONSTRAINT_TYPE = 'PRIMARY KEY'
              AND tc.TABLE_SCHEMA = ? AND tc.TABLE_NAME = ?
            ORDER BY kcu.ORDINAL_POSITION
        """
        cursor = self.connection.cursor()
        try:
            cursor.execute(query, (schema_name, table_name))
            return [row[0] for row in cursor.fetchall()]
        finally:
            cursor.close()

    def _foreign_keys(self, schema_name: str, table_name: str):
        query = """
            SELECT fk.name, pc.name, rs.name, rt.name, rc.name
            FROM sys.foreign_keys fk
            JOIN sys.foreign_key_columns fkc ON fk.object_id = fkc.constraint_object_id
            JOIN sys.tables pt ON fkc.parent_object_id = pt.object_id
            JOIN sys.schemas ps ON pt.schema_id = ps.schema_id
            JOIN sys.columns pc ON pc.object_id = pt.object_id AND pc.column_id = fkc.parent_column_id
            JOIN sys.tables rt ON fkc.referenced_object_id = rt.object_id
            JOIN sys.schemas rs ON rt.schema_id = rs.schema_id
            JOIN sys.columns rc ON rc.object_id = rt.object_id AND rc.column_id = fkc.referenced_column_id
            WHERE ps.name = ? AND pt.name = ?
            ORDER BY fk.name, fkc.constraint_column_id
        """
        cursor = self.connection.cursor()
        try:
            cursor.execute(query, (schema_name, table_name))
            rows = cursor.fetchall()
        finally:
            cursor.close()
        return [
            {
                "constraint_name": row[0],
                "source_schema": schema_name,
                "source_table": table_name,
                "source_column": row[1],
                "target_schema": row[2],
                "target_table": row[3],
                "target_column": row[4],
            }
            for row in rows
        ]
