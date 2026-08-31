from __future__ import annotations

from typing import Any

from src.connectors.base import DatabaseConnector
from src.connectors.common import apply_key_flags, new_column, new_object


class MySQLConnector(DatabaseConnector):
    """MySQL connector for connection testing and complete metadata discovery."""

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
        """Discover all supported MySQL database objects."""
        database_name = self.config["database_name"]

        objects = self._discover_tables_and_views(database_name)
        objects.extend(self._discover_routines(database_name))
        objects.extend(self._discover_triggers(database_name))

        return objects

    def _discover_tables_and_views(self, database_name: str):
        query = """
            SELECT
                t.TABLE_SCHEMA,
                t.TABLE_NAME,
                t.TABLE_TYPE,
                t.ENGINE,
                t.TABLE_ROWS,
                t.TABLE_COLLATION,
                t.TABLE_COMMENT,
                v.VIEW_DEFINITION
            FROM information_schema.TABLES AS t
            LEFT JOIN information_schema.VIEWS AS v
              ON v.TABLE_SCHEMA = t.TABLE_SCHEMA
             AND v.TABLE_NAME = t.TABLE_NAME
            WHERE t.TABLE_SCHEMA = %s
              AND t.TABLE_TYPE IN ('BASE TABLE', 'VIEW')
            ORDER BY t.TABLE_NAME
        """
        cursor = self.connection.cursor()
        try:
            cursor.execute(query, (database_name,))
            rows = cursor.fetchall()
        finally:
            cursor.close()

        objects = []
        for row in rows:
            (
                schema_name,
                object_name,
                table_type,
                engine,
                estimated_rows,
                collation,
                comment,
                view_definition,
            ) = row

            object_type = "TABLE" if table_type == "BASE TABLE" else "VIEW"
            object_ddl = self._get_table_or_view_ddl(
                schema_name,
                object_name,
                object_type,
            )
            metadata = {
                "source_table_type": table_type,
                "engine": engine,
                "estimated_rows": estimated_rows,
                "collation": collation,
                "comment": comment or None,
            }
            if object_type == "VIEW":
                metadata["view_definition"] = view_definition

            item = new_object(
                schema_name=schema_name,
                object_name=object_name,
                object_type=object_type,
                object_ddl=object_ddl,
                metadata=metadata,
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

    def _discover_routines(self, database_name: str):
        query = """
            SELECT
                ROUTINE_SCHEMA,
                ROUTINE_NAME,
                ROUTINE_TYPE,
                DATA_TYPE,
                SQL_DATA_ACCESS,
                IS_DETERMINISTIC,
                SECURITY_TYPE,
                ROUTINE_COMMENT
            FROM information_schema.ROUTINES
            WHERE ROUTINE_SCHEMA = %s
            ORDER BY ROUTINE_TYPE, ROUTINE_NAME
        """
        cursor = self.connection.cursor()
        try:
            cursor.execute(query, (database_name,))
            rows = cursor.fetchall()
        finally:
            cursor.close()

        routines = []
        for row in rows:
            (
                schema_name,
                routine_name,
                routine_type,
                return_type,
                sql_data_access,
                deterministic,
                security_type,
                comment,
            ) = row
            object_type = "PROCEDURE" if routine_type == "PROCEDURE" else "FUNCTION"
            routines.append(
                new_object(
                    schema_name=schema_name,
                    object_name=routine_name,
                    object_type=object_type,
                    object_ddl=self._get_routine_ddl(
                        schema_name,
                        routine_name,
                        object_type,
                    ),
                    metadata={
                        "return_type": return_type,
                        "sql_data_access": sql_data_access,
                        "is_deterministic": deterministic,
                        "security_type": security_type,
                        "comment": comment or None,
                    },
                )
            )

        return routines
    
    def _discover_triggers(
        self,
        database_name: str,
    ) -> list[dict[str, Any]]:
        """Discover user-defined MySQL triggers."""

        query = """
            SELECT
                TRIGGER_SCHEMA,
                TRIGGER_NAME,
                EVENT_MANIPULATION,
                EVENT_OBJECT_SCHEMA,
                EVENT_OBJECT_TABLE,
                ACTION_ORDER,
                ACTION_CONDITION,
                ACTION_STATEMENT,
                ACTION_ORIENTATION,
                ACTION_TIMING,
                CREATED,
                SQL_MODE,
                DEFINER
            FROM information_schema.TRIGGERS
            WHERE TRIGGER_SCHEMA = %s
            ORDER BY TRIGGER_NAME
        """

        cursor = self.connection.cursor()

        try:
            cursor.execute(query, (database_name,))
            rows = cursor.fetchall()
        finally:
            cursor.close()

        triggers = []

        for row in rows:
            (
                trigger_schema,
                trigger_name,
                event_manipulation,
                event_object_schema,
                event_object_table,
                action_order,
                action_condition,
                action_statement,
                action_orientation,
                action_timing,
                created_at,
                sql_mode,
                definer,
            ) = row

            trigger_ddl = self._get_trigger_ddl(
                schema_name=trigger_schema,
                trigger_name=trigger_name,
                fallback_statement=action_statement,
            )

            trigger = new_object(
                schema_name=trigger_schema,
                object_name=trigger_name,
                object_type="TRIGGER",
                object_ddl=trigger_ddl,
                metadata={
                    "language": "SQL",
                    "parameter_count": 0,
                    "last_altered_at": created_at,
                    "return_type": None,
                    "materialized": False,
                    "enabled": True,
                    "trigger_table_schema": event_object_schema,
                    "trigger_table": event_object_table,
                    "trigger_timing": action_timing,
                    "trigger_events": [
                        event_manipulation
                    ],
                    "orientation": action_orientation,
                    "action_order": action_order,
                    "action_condition": action_condition,
                    "sql_mode": sql_mode,
                    "definer": definer,
                },
            )

            triggers.append(trigger)

        return triggers

    def _columns(self, schema_name: str, object_name: str):
        query = """
            SELECT
                COLUMN_NAME,
                ORDINAL_POSITION,
                COLUMN_TYPE,
                IS_NULLABLE,
                COLUMN_DEFAULT,
                DATA_TYPE,
                CHARACTER_SET_NAME,
                COLLATION_NAME,
                COLUMN_KEY,
                EXTRA,
                COLUMN_COMMENT,
                GENERATION_EXPRESSION
            FROM information_schema.COLUMNS
            WHERE TABLE_SCHEMA = %s
              AND TABLE_NAME = %s
            ORDER BY ORDINAL_POSITION
        """
        cursor = self.connection.cursor()
        try:
            cursor.execute(query, (schema_name, object_name))
            rows = cursor.fetchall()
        finally:
            cursor.close()

        columns = []
        for row in rows:
            column = new_column(
                column_name=row[0],
                ordinal_position=row[1],
                data_type=str(row[2]).upper(),
                nullable=row[3] == "YES",
                default_value=row[4],
                native_data_type=row[5],
            )
            column["column_metadata"] = {
                "character_set": row[6],
                "collation": row[7],
                "column_key": row[8] or None,
                "extra": row[9] or None,
                "comment": row[10] or None,
                "generation_expression": row[11] or None,
                "auto_increment": "auto_increment" in (row[9] or "").lower(),
                "generated": bool(row[11]),
            }
            columns.append(column)
        return columns

    def _primary_keys(self, schema_name: str, table_name: str):
        query = """
            SELECT COLUMN_NAME
            FROM information_schema.KEY_COLUMN_USAGE
            WHERE TABLE_SCHEMA = %s
              AND TABLE_NAME = %s
              AND CONSTRAINT_NAME = 'PRIMARY'
            ORDER BY ORDINAL_POSITION
        """
        cursor = self.connection.cursor()
        try:
            cursor.execute(query, (schema_name, table_name))
            return [row[0] for row in cursor.fetchall()]
        finally:
            cursor.close()

    def _foreign_keys(self, schema_name: str, table_name: str):
        query = """
            SELECT
                CONSTRAINT_NAME,
                COLUMN_NAME,
                REFERENCED_TABLE_SCHEMA,
                REFERENCED_TABLE_NAME,
                REFERENCED_COLUMN_NAME,
                POSITION_IN_UNIQUE_CONSTRAINT
            FROM information_schema.KEY_COLUMN_USAGE
            WHERE TABLE_SCHEMA = %s
              AND TABLE_NAME = %s
              AND REFERENCED_TABLE_NAME IS NOT NULL
            ORDER BY CONSTRAINT_NAME, ORDINAL_POSITION
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
                "position_in_unique_constraint": row[5],
            }
            for row in rows
        ]

    def _get_table_or_view_ddl(
        self,
        schema_name: str,
        object_name: str,
        object_type: str,
    ) -> str | None:
        keyword = "VIEW" if object_type == "VIEW" else "TABLE"
        query = (
            f"SHOW CREATE {keyword} "
            f"{self._quote(schema_name)}.{self._quote(object_name)}"
        )
        cursor = self.connection.cursor()
        try:
            cursor.execute(query)
            row = cursor.fetchone()
        except Exception:
            return None
        finally:
            cursor.close()

        if not row:
            return None
        return str(row[1]) if len(row) > 1 and row[1] is not None else None

    def _get_routine_ddl(
        self,
        schema_name: str,
        routine_name: str,
        object_type: str,
    ) -> str | None:
        query = (
            f"SHOW CREATE {object_type} "
            f"{self._quote(schema_name)}.{self._quote(routine_name)}"
        )
        cursor = self.connection.cursor()
        try:
            cursor.execute(query)
            row = cursor.fetchone()
        except Exception:
            return None
        finally:
            cursor.close()

        if not row:
            return None
        for value in row[1:]:
            if isinstance(value, str) and "CREATE" in value.upper():
                return value
        return None
    
    def _get_trigger_ddl(
        self,
        schema_name: str,
        trigger_name: str,
        fallback_statement: str | None = None,
    ) -> str | None:
        """Return the complete trigger definition when permitted."""

        query = (
            "SHOW CREATE TRIGGER "
            f"{self._quote(schema_name)}."
            f"{self._quote(trigger_name)}"
        )

        cursor = self.connection.cursor()

        try:
            cursor.execute(query)
            row = cursor.fetchone()
        except Exception:
            return fallback_statement
        finally:
            cursor.close()

        if not row:
            return fallback_statement

        for value in row[1:]:
            if (
                isinstance(value, str)
                and "TRIGGER" in value.upper()
            ):
                return value

        return fallback_statement

    @staticmethod
    def _quote(identifier: str) -> str:
        return "`" + identifier.replace("`", "``") + "`"
