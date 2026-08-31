from __future__ import annotations

from typing import Any

from src.connectors.base import DatabaseConnector
from src.connectors.common import apply_key_flags, new_column, new_object
from src.connectors.object_metadata import (
    normalize_object_metadata,
)

class PostgreSQLConnector(DatabaseConnector):
    @property
    def health_query(self) -> str:
        return "SELECT 1"

    def connect(self):
        import psycopg

        self.connection = psycopg.connect(
            host=self.config["host"],
            port=int(self.config.get("port", 5432)),
            dbname=self.config["database_name"],
            user=self.config["username"],
            password=self.password,
            sslmode="require" if self.config.get("ssl_enabled") else "prefer",
            connect_timeout=10,
        )
        return self.connection

    def make_read_only(self) -> None:
        self.connection.execute(
            "SET SESSION CHARACTERISTICS AS TRANSACTION READ ONLY"
        )

    def execute_one(self, query: str) -> Any:
        with self.connection.cursor() as cursor:
            cursor.execute(query)
            return cursor.fetchone()

    def discover_metadata(self) -> list[dict[str, Any]]:
        schema_filter = self.config.get("schema_name")
        query = """
            SELECT table_schema, table_name, table_type
            FROM information_schema.tables
            WHERE table_schema NOT IN ('information_schema', 'pg_catalog', 'pg_toast')
              AND table_schema NOT LIKE 'pg_temp_%%'
              AND table_schema NOT LIKE 'pg_toast_temp_%%'
              AND table_type IN ('BASE TABLE', 'VIEW')
        """
        params: list[Any] = []
        if schema_filter:
            query += " AND table_schema = %s"
            params.append(schema_filter)
        query += " ORDER BY table_schema, table_name "

        with self.connection.cursor() as cursor:
            cursor.execute(query, params)
            rows = cursor.fetchall()

        objects = []
        for schema_name, object_name, table_type in rows:
            object_type = "TABLE" if table_type == "BASE TABLE" else "VIEW"
            item = new_object(
                schema_name,
                object_name,
                object_type,
                metadata={"source_table_type": table_type},
            )
            item["columns"] = self._columns(schema_name, object_name)
            if object_type == "TABLE":
                item["primary_key_columns"] = self._primary_keys(schema_name, object_name)
                item["foreign_keys"] = self._foreign_keys(schema_name, object_name)
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
        
        """Discover user-defined PostgreSQL triggers."""

        query = """
            SELECT
                trigger_namespace.nspname
                    AS trigger_schema,
                trigger_info.tgname
                    AS trigger_name,
                table_namespace.nspname
                    AS table_schema,
                table_info.relname
                    AS table_name,
                pg_get_triggerdef(
                    trigger_info.oid,
                    TRUE
                ) AS trigger_ddl,
                trigger_info.tgenabled
                    AS enabled_code,
                function_namespace.nspname
                    AS function_schema,
                function_info.proname
                    AS function_name,
                language_info.lanname
                    AS function_language
            FROM pg_trigger AS trigger_info

            JOIN pg_class AS table_info
              ON table_info.oid =
                 trigger_info.tgrelid

            JOIN pg_namespace AS table_namespace
              ON table_namespace.oid =
                 table_info.relnamespace

            JOIN pg_namespace AS trigger_namespace
              ON trigger_namespace.oid =
                 table_info.relnamespace

            JOIN pg_proc AS function_info
              ON function_info.oid =
                 trigger_info.tgfoid

            JOIN pg_namespace AS function_namespace
              ON function_namespace.oid =
                 function_info.pronamespace

            JOIN pg_language AS language_info
              ON language_info.oid =
                 function_info.prolang

            WHERE trigger_info.tgisinternal = FALSE
              AND table_namespace.nspname NOT IN (
                  'pg_catalog',
                  'information_schema',
                  'pg_toast'
              )
              AND table_namespace.nspname
                  NOT LIKE 'pg_temp_%%'
              AND table_namespace.nspname
                  NOT LIKE 'pg_toast_temp_%%'
        """

        parameters: list[Any] = []

        if schema_filter:
            query += """
              AND table_namespace.nspname = %s
            """
            parameters.append(schema_filter)

        query += """
            ORDER BY
                trigger_namespace.nspname,
                trigger_info.tgname
        """

        with self.connection.cursor() as cursor:
            cursor.execute(query, parameters)
            rows = cursor.fetchall()

        triggers: list[dict[str, Any]] = []

        for row in rows:
            (
                trigger_schema,
                trigger_name,
                table_schema,
                table_name,
                trigger_ddl,
                enabled_code,
                function_schema,
                function_name,
                function_language,
            ) = row
            

            trigger_details = (
                self._parse_trigger_definition(
                    trigger_ddl
                )
            )

            trigger = new_object(
                schema_name=trigger_schema,
                object_name=trigger_name,
                object_type="TRIGGER",
                object_ddl=trigger_ddl,
                metadata={
                    "language": (
                        str(function_language).upper()
                        if function_language
                        else "PLPGSQL"
                    ),
                    "parameter_count": 0,
                    "last_altered_at": None,
                    "return_type": None,
                    "materialized": False,
                    "enabled": enabled_code != "D",
                    "enabled_code": enabled_code,
                    "trigger_table_schema": table_schema,
                    "trigger_table": table_name,
                    "trigger_function_schema": (
                        function_schema
                    ),
                    "trigger_function": function_name,
                    "trigger_timing": (
                        trigger_details["timing"]
                    ),
                    "trigger_events": (
                        trigger_details["events"]
                    ),
                    "orientation": (
                        trigger_details["orientation"]
                    ),
                },
            )

            triggers.append(trigger)

        return triggers

    @staticmethod
    def _parse_trigger_definition(
        trigger_ddl: str | None,
    ) -> dict[str, Any]:
        """Extract basic properties from pg_get_triggerdef output."""

        definition = str(trigger_ddl or "")
        normalized = definition.upper()

        timing = None

        for candidate in (
            "BEFORE",
            "AFTER",
            "INSTEAD OF",
        ):
            if candidate in normalized:
                timing = candidate
                break

        events = []

        for event_name in (
            "INSERT",
            "UPDATE",
            "DELETE",
            "TRUNCATE",
        ):
            if event_name in normalized:
                events.append(event_name)

        orientation = None

        if "FOR EACH ROW" in normalized:
            orientation = "ROW"
        elif "FOR EACH STATEMENT" in normalized:
            orientation = "STATEMENT"

        return {
            "timing": timing,
            "events": events,
            "orientation": orientation,
        }

    def _columns(self, schema_name: str, object_name: str):
        query = """
            SELECT column_name, ordinal_position, data_type, is_nullable,
                   column_default, udt_name
            FROM information_schema.columns
            WHERE table_schema = %s AND table_name = %s
            ORDER BY ordinal_position
        """
        with self.connection.cursor() as cursor:
            cursor.execute(query, (schema_name, object_name))
            rows = cursor.fetchall()
        return [
            new_column(row[0], row[1], row[2].upper(), row[3] == "YES", row[4], row[5])
            for row in rows
        ]

    def _primary_keys(self, schema_name: str, table_name: str):
        query = """
            SELECT kcu.column_name
            FROM information_schema.table_constraints tc
            JOIN information_schema.key_column_usage kcu
              ON tc.constraint_name = kcu.constraint_name
             AND tc.constraint_schema = kcu.constraint_schema
            WHERE tc.constraint_type = 'PRIMARY KEY'
              AND tc.table_schema = %s AND tc.table_name = %s
            ORDER BY kcu.ordinal_position
        """
        with self.connection.cursor() as cursor:
            cursor.execute(query, (schema_name, table_name))
            return [row[0] for row in cursor.fetchall()]

    def _foreign_keys(self, schema_name: str, table_name: str):
        query = """
            SELECT kcu.constraint_name, kcu.column_name,
                   ccu.table_schema, ccu.table_name, ccu.column_name
            FROM information_schema.table_constraints tc
            JOIN information_schema.key_column_usage kcu
              ON tc.constraint_name = kcu.constraint_name
             AND tc.constraint_schema = kcu.constraint_schema
            JOIN information_schema.constraint_column_usage ccu
              ON tc.constraint_name = ccu.constraint_name
             AND tc.constraint_schema = ccu.constraint_schema
            WHERE tc.constraint_type = 'FOREIGN KEY'
              AND tc.table_schema = %s AND tc.table_name = %s
            ORDER BY kcu.constraint_name, kcu.ordinal_position
        """
        with self.connection.cursor() as cursor:
            cursor.execute(query, (schema_name, table_name))
            rows = cursor.fetchall()
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
