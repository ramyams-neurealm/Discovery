from __future__ import annotations

from typing import Any

from src.connectors.base import DatabaseConnector
from src.connectors.common import apply_key_flags, new_column, new_object
from src.connectors.object_metadata import normalize_object_metadata

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

    def list_objects(self) -> list[dict[str, str]]:
        """List selectable MySQL objects without rich metadata."""
        database_name = self.config["database_name"]
        query = """
            SELECT TABLE_SCHEMA, TABLE_NAME,
                   CASE WHEN TABLE_TYPE = 'BASE TABLE' THEN 'TABLE' ELSE 'VIEW' END
            FROM information_schema.TABLES
            WHERE TABLE_SCHEMA = %s AND TABLE_TYPE IN ('BASE TABLE', 'VIEW')
            UNION ALL
            SELECT ROUTINE_SCHEMA, ROUTINE_NAME, ROUTINE_TYPE
            FROM information_schema.ROUTINES WHERE ROUTINE_SCHEMA = %s
            UNION ALL
            SELECT TRIGGER_SCHEMA, TRIGGER_NAME, 'TRIGGER'
            FROM information_schema.TRIGGERS WHERE TRIGGER_SCHEMA = %s
            ORDER BY 1, 3, 2
        """
        cursor = self.connection.cursor()
        try:
            cursor.execute(query, (database_name, database_name, database_name))
            rows = cursor.fetchall()
        finally:
            cursor.close()
        return [
            {"schema_name": str(row[0]), "object_name": str(row[1]), "object_type": str(row[2]).upper()}
            for row in rows
        ]

    def discover_metadata(
        self,
        selected_objects: list[dict[str, str]] | None = None,
    ) -> list[dict[str, Any]]:
        """Discover MySQL objects, optionally limited to a selected set."""
        database_name = self.config["database_name"]
        selection = self._selection_by_type(selected_objects)
        objects = self._discover_tables_and_views(database_name, selection)
        objects.extend(self._discover_routines(database_name, selection))
        objects.extend(self._discover_triggers(database_name, selection))
        self._validate_selected_objects(selected_objects, objects)
        return objects

    @staticmethod
    def _selection_by_type(
        selected_objects: list[dict[str, str]] | None,
    ) -> dict[str, set[str]]:
        selection: dict[str, set[str]] = {}
        for item in selected_objects or []:
            object_type = str(item.get("object_type") or "").upper()
            object_name = str(item.get("object_name") or "")
            if object_type and object_name:
                selection.setdefault(object_type, set()).add(object_name)
        return selection

    @staticmethod
    def _is_selected(
        selection: dict[str, set[str]],
        object_type: str,
        object_name: str,
    ) -> bool:
        return not selection or object_name in selection.get(object_type, set())

    @staticmethod
    def _validate_selected_objects(
        selected_objects: list[dict[str, str]] | None,
        discovered_objects: list[dict[str, Any]],
    ) -> None:
        if not selected_objects:
            return
        requested = {
            (str(item.get("object_type") or "").upper(), str(item.get("object_name") or ""))
            for item in selected_objects
        }
        discovered = {
            (str(item.get("object_type") or "").upper(), str(item.get("object_name") or ""))
            for item in discovered_objects
        }
        missing = sorted(requested - discovered)
        if missing:
            formatted = ", ".join(f"{kind}:{name}" for kind, name in missing)
            raise ValueError(
                "Selected objects were not found in the configured "
                f"MySQL database: {formatted}"
            )

    def _discover_tables_and_views(
        self,
        database_name: str,
        selection: dict[str, set[str]] | None = None,
    ) -> list[dict[str, Any]]:
        """Discover MySQL tables and views with richer metadata."""

        query = """
            SELECT
                table_info.TABLE_SCHEMA,
                table_info.TABLE_NAME,
                table_info.TABLE_TYPE,
                table_info.ENGINE,
                table_info.TABLE_ROWS,
                table_info.TABLE_COLLATION,
                table_info.TABLE_COMMENT,
                view_info.VIEW_DEFINITION,
                table_info.CREATE_TIME,
                table_info.UPDATE_TIME,
                table_info.DATA_LENGTH,
                table_info.INDEX_LENGTH
            FROM information_schema.TABLES AS table_info

            LEFT JOIN information_schema.VIEWS AS view_info
              ON view_info.TABLE_SCHEMA =
                 table_info.TABLE_SCHEMA
             AND view_info.TABLE_NAME =
                 table_info.TABLE_NAME

            WHERE table_info.TABLE_SCHEMA = %s
              AND table_info.TABLE_TYPE IN (
                  'BASE TABLE',
                  'VIEW'
              )

            ORDER BY table_info.TABLE_NAME
        """

        cursor = self.connection.cursor()

        try:
            cursor.execute(
                query,
                (database_name,),
            )
            rows = cursor.fetchall()
        finally:
            cursor.close()

        objects: list[dict[str, Any]] = []

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
                created_at,
                last_altered_at,
                data_length,
                index_length,
            ) = row

            object_type = (
                "TABLE"
                if table_type == "BASE TABLE"
                else "VIEW"
            )

            if not self._is_selected(
                selection or {}, object_type, str(object_name)
            ):
                continue

            object_ddl = self._get_table_or_view_ddl(
                schema_name=schema_name,
                object_name=object_name,
                object_type=object_type,
            )

            estimated_size_bytes = (
                int(data_length or 0)
                + int(index_length or 0)
            )

            metadata = {
                "source_table_type": table_type,
                "engine": engine,
                "estimated_rows": estimated_rows,
                "estimated_size_bytes": (
                    estimated_size_bytes
                ),
                "data_length_bytes": data_length,
                "index_length_bytes": index_length,
                "collation": collation,
                "comment": comment or None,
                "created_at": created_at,
                "last_altered_at": last_altered_at,
                "language": (
                    "SQL"
                    if object_type == "VIEW"
                    else None
                ),
                "parameter_count": 0,
                "return_type": None,
                "materialized": False,
                "enabled": True,
            }

            if object_type == "VIEW":
                metadata["view_definition"] = (
                    view_definition
                )

            item = new_object(
                schema_name=schema_name,
                object_name=object_name,
                object_type=object_type,
                object_ddl=object_ddl,
                metadata=metadata,
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

            # Recalculate complexity after discovering columns
            # and foreign keys.
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

    def _discover_routines(
        self,
        database_name: str,
        selection: dict[str, set[str]] | None = None,
    ) -> list[dict[str, Any]]:
        """Discover MySQL procedures and functions with rich metadata."""

        query = """
            SELECT
                routine_info.ROUTINE_SCHEMA,
                routine_info.ROUTINE_NAME,
                routine_info.SPECIFIC_NAME,
                routine_info.ROUTINE_TYPE,
                routine_info.DATA_TYPE,
                routine_info.DTD_IDENTIFIER,
                routine_info.ROUTINE_BODY,
                routine_info.EXTERNAL_LANGUAGE,
                routine_info.SQL_DATA_ACCESS,
                routine_info.IS_DETERMINISTIC,
                routine_info.SECURITY_TYPE,
                routine_info.ROUTINE_COMMENT,
                routine_info.CREATED,
                routine_info.LAST_ALTERED,
                routine_info.SQL_MODE,
                routine_info.DEFINER,
                (
                    SELECT COUNT(*)
                    FROM information_schema.PARAMETERS
                        AS parameter_info
                    WHERE parameter_info.SPECIFIC_SCHEMA =
                          routine_info.ROUTINE_SCHEMA
                      AND parameter_info.SPECIFIC_NAME =
                          routine_info.SPECIFIC_NAME
                      AND parameter_info.ORDINAL_POSITION > 0
                ) AS PARAMETER_COUNT
            FROM information_schema.ROUTINES
                AS routine_info

            WHERE routine_info.ROUTINE_SCHEMA = %s

            ORDER BY
                routine_info.ROUTINE_TYPE,
                routine_info.ROUTINE_NAME
        """

        cursor = self.connection.cursor()

        try:
            cursor.execute(
                query,
                (database_name,),
            )
            rows = cursor.fetchall()
        finally:
            cursor.close()

        routines: list[dict[str, Any]] = []

        for row in rows:
            (
                schema_name,
                routine_name,
                specific_name,
                routine_type,
                basic_return_type,
                detailed_return_type,
                routine_body,
                external_language,
                sql_data_access,
                deterministic,
                security_type,
                comment,
                created_at,
                last_altered_at,
                sql_mode,
                definer,
                parameter_count,
            ) = row

            object_type = (
                "PROCEDURE"
                if routine_type == "PROCEDURE"
                else "FUNCTION"
            )

            if not self._is_selected(
                selection or {}, object_type, str(routine_name)
            ):
                continue

            object_ddl = self._get_routine_ddl(
                schema_name=schema_name,
                routine_name=routine_name,
                object_type=object_type,
            )

            language = (
                str(external_language).strip()
                if external_language
                else str(routine_body or "SQL").strip()
            )

            return_type = None

            if object_type == "FUNCTION":
                return_type = (
                    detailed_return_type
                    or basic_return_type
                )

            routine = new_object(
                schema_name=schema_name,
                object_name=routine_name,
                object_type=object_type,
                object_ddl=object_ddl,
                metadata={
                    "language": language.upper(),
                    "parameter_count": int(
                        parameter_count or 0
                    ),
                    "return_type": return_type,
                    "created_at": created_at,
                    "last_altered_at": last_altered_at,
                    "materialized": False,
                    "enabled": True,
                    "specific_name": specific_name,
                    "sql_data_access": sql_data_access,
                    "is_deterministic": (
                        str(
                            deterministic or ""
                        ).upper() == "YES"
                    ),
                    "security_type": security_type,
                    "comment": comment or None,
                    "sql_mode": sql_mode,
                    "definer": definer,
                },
            )

            routines.append(routine)

        return routines
    
    def _discover_triggers(
        self,
        database_name: str,
        selection: dict[str, set[str]] | None = None,
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

            if not self._is_selected(
                selection or {}, "TRIGGER", str(trigger_name)
            ):
                continue

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
