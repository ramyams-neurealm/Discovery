from __future__ import annotations

from typing import Any

from src.connectors.base import DatabaseConnector
from src.connectors.common import apply_key_flags, new_column, new_object


class OracleConnector(DatabaseConnector):
    @property
    def health_query(self) -> str:
        return "SELECT 1 FROM DUAL"

    def connect(self):
        import oracledb

        dsn = oracledb.makedsn(
            self.config["host"],
            int(self.config.get("port", 1521)),
            service_name=self.config["database_name"],
        )
        self.connection = oracledb.connect(
            user=self.config["username"],
            password=self.password,
            dsn=dsn,
        )
        return self.connection

    def make_read_only(self) -> None:
        cursor = self.connection.cursor()
        try:
            cursor.execute("SET TRANSACTION READ ONLY")
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
        owner = (self.config.get("schema_name") or self.config["username"]).upper()
        query = """
            SELECT OWNER, OBJECT_NAME, OBJECT_TYPE
            FROM ALL_OBJECTS
            WHERE OWNER = :owner
              AND OBJECT_TYPE IN ('TABLE', 'VIEW', 'MATERIALIZED VIEW', 'PROCEDURE', 'FUNCTION')
            ORDER BY OBJECT_TYPE, OBJECT_NAME
        """
        cursor = self.connection.cursor()
        try:
            cursor.execute(query, owner=owner)
            rows = cursor.fetchall()
        finally:
            cursor.close()

        type_map = {
            "MATERIALIZED VIEW": "MATERIALIZED_VIEW",
            "PROCEDURE": "PROCEDURE",
            "FUNCTION": "FUNCTION",
        }
        objects = []
        for schema_name, object_name, source_type in rows:
            object_type = type_map.get(source_type, source_type)
            item = new_object(schema_name, object_name, object_type)
            if object_type in {"TABLE", "VIEW", "MATERIALIZED_VIEW"}:
                item["columns"] = self._columns(schema_name, object_name)
            if object_type == "TABLE":
                item["primary_key_columns"] = self._primary_keys(schema_name, object_name)
                item["foreign_keys"] = self._foreign_keys(schema_name, object_name)
                apply_key_flags(item)
            objects.append(item)
        return objects

    def _columns(self, schema_name: str, object_name: str):
        query = """
            SELECT COLUMN_NAME, COLUMN_ID, DATA_TYPE, NULLABLE, DATA_DEFAULT,
                   DATA_LENGTH, DATA_PRECISION, DATA_SCALE
            FROM ALL_TAB_COLUMNS
            WHERE OWNER = :owner AND TABLE_NAME = :table_name
            ORDER BY COLUMN_ID
        """
        cursor = self.connection.cursor()
        try:
            cursor.execute(query, owner=schema_name, table_name=object_name)
            rows = cursor.fetchall()
        finally:
            cursor.close()
        result = []
        for row in rows:
            data_type = str(row[2]).upper()
            if data_type in {"VARCHAR2", "CHAR", "NVARCHAR2", "NCHAR"} and row[5]:
                data_type = f"{data_type}({row[5]})"
            elif data_type == "NUMBER" and row[6] is not None:
                data_type = f"NUMBER({row[6]},{row[7] or 0})"
            result.append(new_column(row[0], row[1], data_type, row[3] == "Y", row[4], row[2]))
        return result

    def _primary_keys(self, schema_name: str, table_name: str):
        query = """
            SELECT cols.COLUMN_NAME
            FROM ALL_CONSTRAINTS cons
            JOIN ALL_CONS_COLUMNS cols
              ON cons.OWNER = cols.OWNER AND cons.CONSTRAINT_NAME = cols.CONSTRAINT_NAME
            WHERE cons.CONSTRAINT_TYPE = 'P'
              AND cons.OWNER = :owner AND cons.TABLE_NAME = :table_name
            ORDER BY cols.POSITION
        """
        cursor = self.connection.cursor()
        try:
            cursor.execute(query, owner=schema_name, table_name=table_name)
            return [row[0] for row in cursor.fetchall()]
        finally:
            cursor.close()

    def _foreign_keys(self, schema_name: str, table_name: str):
        query = """
            SELECT fk.CONSTRAINT_NAME, fkc.COLUMN_NAME,
                   pk.OWNER, pk.TABLE_NAME, pkc.COLUMN_NAME
            FROM ALL_CONSTRAINTS fk
            JOIN ALL_CONS_COLUMNS fkc
              ON fk.OWNER = fkc.OWNER AND fk.CONSTRAINT_NAME = fkc.CONSTRAINT_NAME
            JOIN ALL_CONSTRAINTS pk
              ON fk.R_OWNER = pk.OWNER AND fk.R_CONSTRAINT_NAME = pk.CONSTRAINT_NAME
            JOIN ALL_CONS_COLUMNS pkc
              ON pk.OWNER = pkc.OWNER AND pk.CONSTRAINT_NAME = pkc.CONSTRAINT_NAME
             AND fkc.POSITION = pkc.POSITION
            WHERE fk.CONSTRAINT_TYPE = 'R'
              AND fk.OWNER = :owner AND fk.TABLE_NAME = :table_name
            ORDER BY fk.CONSTRAINT_NAME, fkc.POSITION
        """
        cursor = self.connection.cursor()
        try:
            cursor.execute(query, owner=schema_name, table_name=table_name)
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
