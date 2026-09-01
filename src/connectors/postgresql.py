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
        """
        Discover PostgreSQL tables, views, materialized views,
        procedures, functions, and triggers.
        """

        schema_filter = self.config.get("schema_name")

        objects = self._discover_tables_and_views(
            schema_filter=schema_filter,
        )

        objects.extend(
            self._discover_routines(
                schema_filter=schema_filter,
            )
        )

        objects.extend(
            self._discover_triggers(
                schema_filter=schema_filter,
            )
        )

        return objects

    def _discover_tables_and_views(
        self,
        schema_filter: str | None = None,
    ) -> list[dict[str, Any]]:
        """
        Discover PostgreSQL tables, views, and materialized views.
        """

        query = """
            SELECT
                namespace_info.nspname AS schema_name,
                relation_info.relname AS object_name,
                relation_info.relkind AS relation_kind,
                relation_info.reltuples::BIGINT
                    AS estimated_rows,
                pg_total_relation_size(
                    relation_info.oid
                ) AS estimated_size_bytes,
                obj_description(
                    relation_info.oid,
                    'pg_class'
                ) AS object_comment
            FROM pg_class AS relation_info

            JOIN pg_namespace AS namespace_info
              ON namespace_info.oid =
                 relation_info.relnamespace

            WHERE relation_info.relkind IN (
                'r',
                'p',
                'v',
                'm'
            )
              AND namespace_info.nspname NOT IN (
                  'information_schema',
                  'pg_catalog',
                  'pg_toast'
              )
              AND namespace_info.nspname
                  NOT LIKE 'pg_temp_%%'
              AND namespace_info.nspname
                  NOT LIKE 'pg_toast_temp_%%'
        """

        parameters: list[Any] = []

        if schema_filter:
            query += """
              AND namespace_info.nspname = %s
            """
            parameters.append(schema_filter)

        query += """
            ORDER BY
                namespace_info.nspname,
                relation_info.relname
        """

        with self.connection.cursor() as cursor:
            cursor.execute(query, parameters)
            rows = cursor.fetchall()

        objects: list[dict[str, Any]] = []

        relation_type_mapping = {
            "r": "TABLE",
            "p": "TABLE",
            "v": "VIEW",
            "m": "MATERIALIZED_VIEW",
        }

        source_type_mapping = {
            "r": "BASE TABLE",
            "p": "PARTITIONED TABLE",
            "v": "VIEW",
            "m": "MATERIALIZED VIEW",
        }

        for row in rows:
            schema_name = str(row[0])
            object_name = str(row[1])
            relation_kind = str(row[2])
            estimated_rows = row[3]
            estimated_size_bytes = row[4]
            object_comment = row[5]

            object_type = relation_type_mapping[
                relation_kind
            ]

            object_ddl = self._relation_definition(
                schema_name=schema_name,
                object_name=object_name,
                object_type=object_type,
            )

            item = new_object(
                schema_name=schema_name,
                object_name=object_name,
                object_type=object_type,
                object_ddl=object_ddl,
                metadata={
                    "source_table_type": (
                        source_type_mapping[
                            relation_kind
                        ]
                    ),
                    "language": (
                        "SQL"
                        if object_type in {
                            "VIEW",
                            "MATERIALIZED_VIEW",
                        }
                        else None
                    ),
                    "parameter_count": 0,
                    "return_type": None,
                    "materialized": (
                        object_type
                        == "MATERIALIZED_VIEW"
                    ),
                    "enabled": True,
                    "estimated_rows": (
                        int(estimated_rows or 0)
                    ),
                    "estimated_size_bytes": (
                        int(
                            estimated_size_bytes or 0
                        )
                    ),
                    "comment": (
                        str(object_comment)
                        if object_comment
                        else None
                    ),
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

        return objects
    

    def _relation_definition(
        self,
        schema_name: str,
        object_name: str,
        object_type: str,
    ) -> str | None:
        """
        Return a PostgreSQL view or materialized-view definition.

        PostgreSQL does not expose a complete CREATE TABLE statement
        through one simple built-in catalog function, so table DDL
        remains unavailable here.
        """

        if object_type not in {
            "VIEW",
            "MATERIALIZED_VIEW",
        }:
            return None

        query = """
            SELECT pg_get_viewdef(
                relation_info.oid,
                TRUE
            )
            FROM pg_class AS relation_info

            JOIN pg_namespace AS namespace_info
              ON namespace_info.oid =
                 relation_info.relnamespace

            WHERE namespace_info.nspname = %s
              AND relation_info.relname = %s
        """

        with self.connection.cursor() as cursor:
            cursor.execute(
                query,
                (
                    schema_name,
                    object_name,
                ),
            )
            row = cursor.fetchone()

        if not row or row[0] is None:
            return None

        definition = str(row[0]).strip()

        if not definition:
            return None

        quoted_schema = self._quote_identifier(
            schema_name
        )
        quoted_object = self._quote_identifier(
            object_name
        )

        if object_type == "MATERIALIZED_VIEW":
            prefix = (
                "CREATE MATERIALIZED VIEW "
                f"{quoted_schema}.{quoted_object} AS\n"
            )
        else:
            prefix = (
                "CREATE VIEW "
                f"{quoted_schema}.{quoted_object} AS\n"
            )

        return prefix + definition
    
    def _discover_routines(
        self,
        schema_filter: str | None = None,
    ) -> list[dict[str, Any]]:
        """
        Discover PostgreSQL functions and procedures with
        rich routine metadata.
        """

        query = """
            SELECT
                namespace_info.nspname
                    AS schema_name,
                routine_info.proname
                    AS routine_name,
                routine_info.prokind
                    AS routine_kind,
                language_info.lanname
                    AS routine_language,
                routine_info.pronargs
                    AS parameter_count,
                pg_get_function_result(
                    routine_info.oid
                ) AS return_type,
                pg_get_functiondef(
                    routine_info.oid
                ) AS routine_ddl,
                routine_info.provolatile
                    AS volatility_code,
                routine_info.prosecdef
                    AS security_definer,
                routine_info.proleakproof
                    AS leakproof,
                routine_info.proparallel
                    AS parallel_code,
                obj_description(
                    routine_info.oid,
                    'pg_proc'
                ) AS routine_comment
            FROM pg_proc AS routine_info

            JOIN pg_namespace AS namespace_info
              ON namespace_info.oid =
                 routine_info.pronamespace

            JOIN pg_language AS language_info
              ON language_info.oid =
                 routine_info.prolang

            WHERE routine_info.prokind IN (
                'f',
                'p'
            )
              AND namespace_info.nspname NOT IN (
                  'information_schema',
                  'pg_catalog',
                  'pg_toast'
              )
              AND namespace_info.nspname
                  NOT LIKE 'pg_temp_%%'
              AND namespace_info.nspname
                  NOT LIKE 'pg_toast_temp_%%'
        """

        parameters: list[Any] = []

        if schema_filter:
            query += """
              AND namespace_info.nspname = %s
            """
            parameters.append(schema_filter)

        query += """
            ORDER BY
                namespace_info.nspname,
                routine_info.proname
        """

        with self.connection.cursor() as cursor:
            cursor.execute(
                query,
                parameters,
            )
            rows = cursor.fetchall()

        routines: list[dict[str, Any]] = []

        for row in rows:
            schema_name = str(row[0])
            routine_name = str(row[1])
            routine_kind = str(row[2])
            routine_language = str(row[3])
            parameter_count = int(row[4] or 0)

            return_type = (
                str(row[5])
                if row[5] is not None
                else None
            )

            routine_ddl = (
                str(row[6])
                if row[6] is not None
                else None
            )

            volatility_code = str(row[7] or "")
            security_definer = bool(row[8])
            leakproof = bool(row[9])
            parallel_code = str(row[10] or "")

            routine_comment = (
                str(row[11])
                if row[11] is not None
                else None
            )

            object_type = (
                "PROCEDURE"
                if routine_kind == "p"
                else "FUNCTION"
            )

            if object_type == "PROCEDURE":
                return_type = None

            routine = new_object(
                schema_name=schema_name,
                object_name=routine_name,
                object_type=object_type,
                object_ddl=routine_ddl,
                metadata={
                    "language": (
                        routine_language.upper()
                    ),
                    "parameter_count": (
                        parameter_count
                    ),
                    "return_type": return_type,
                    "materialized": False,
                    "enabled": True,
                    "volatility": (
                        self._volatility_name(
                            volatility_code
                        )
                    ),
                    "security_definer": (
                        security_definer
                    ),
                    "leakproof": leakproof,
                    "parallel_safety": (
                        self._parallel_name(
                            parallel_code
                        )
                    ),
                    "comment": routine_comment,
                },
            )

            routines.append(routine)

        return routines

    @staticmethod
    def _volatility_name(
        volatility_code: str,
    ) -> str | None:
        mapping = {
            "i": "IMMUTABLE",
            "s": "STABLE",
            "v": "VOLATILE",
        }

        return mapping.get(
            str(volatility_code or "").lower()
        )

    @staticmethod
    def _parallel_name(
        parallel_code: str,
    ) -> str | None:
        mapping = {
            "s": "SAFE",
            "r": "RESTRICTED",
            "u": "UNSAFE",
        }

        return mapping.get(
            str(parallel_code or "").lower()
        )

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

    @staticmethod
    def _quote_identifier(
        identifier: str,
    ) -> str:
        escaped = str(identifier).replace(
            '"',
            '""',
        )

        return f'"{escaped}"'
