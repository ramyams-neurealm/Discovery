from __future__ import annotations

from typing import Any

from src.connectors.base import DatabaseConnector
from src.connectors.common import apply_key_flags, new_column, new_object


class MySQLConnector(DatabaseConnector):
    @property
    def health_query(self) -> str:
        return "SELECT 1"

    def connect(self):
        import mysql.connector

        self.connection = mysql.connector.connect(
            host=self.config["host"],
            port=int(self.config.get("port", 3306)),
            database=self.config["database_name"],
            user=self.config["username"],
            password=self.password,
            connection_timeout=10,
            ssl_disabled=not self.config.get("ssl_enabled", False),
        )
        return self.connection

    def make_read_only(self) -> None:
        cursor = self.connection.cursor()
        try:
            cursor.execute("SET SESSION TRANSACTION READ ONLY")
        finally:
            cursor.close()

    def execute_one(self, query: str) -> Any:
        cursor = self.connection.cursor()
        try:
            cursor.execute(query)
            return cursor.fetchone()
        finally:
            cursor.close()

    def discover_metadata(self) -> list[dict[str, Any]]:
        database_name = self.config["database_name"]
        query = """
            SELECT table_schema, table_name, table_type
            FROM information_schema.tables
            WHERE table_schema = %s
              AND table_type IN ('BASE TABLE', 'VIEW')
            ORDER BY table_name
        """
        cursor = self.connection.cursor()
        try:
            cursor.execute(query, (database_name,))
            rows = cursor.fetchall()
        finally:
            cursor.close()

        objects = []
        for schema_name, object_name, table_type in rows:
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
            SELECT column_name, ordinal_position, column_type, is_nullable,
                   column_default, data_type
            FROM information_schema.columns
            WHERE table_schema = %s AND table_name = %s
            ORDER BY ordinal_position
        """
        cursor = self.connection.cursor()
        try:
            cursor.execute(query, (schema_name, object_name))
            rows = cursor.fetchall()
        finally:
            cursor.close()
        return [
            new_column(row[0], row[1], row[2].upper(), row[3] == "YES", row[4], row[5])
            for row in rows
        ]

    def _primary_keys(self, schema_name: str, table_name: str):
        query = """
            SELECT column_name
            FROM information_schema.key_column_usage
            WHERE table_schema = %s AND table_name = %s
              AND constraint_name = 'PRIMARY'
            ORDER BY ordinal_position
        """
        cursor = self.connection.cursor()
        try:
            cursor.execute(query, (schema_name, table_name))
            return [row[0] for row in cursor.fetchall()]
        finally:
            cursor.close()

    def _foreign_keys(self, schema_name: str, table_name: str):
        query = """
            SELECT constraint_name, column_name, referenced_table_schema,
                   referenced_table_name, referenced_column_name
            FROM information_schema.key_column_usage
            WHERE table_schema = %s AND table_name = %s
              AND referenced_table_name IS NOT NULL
            ORDER BY constraint_name, ordinal_position
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
