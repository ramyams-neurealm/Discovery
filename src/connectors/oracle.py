from __future__ import annotations

from typing import Any

from src.connectors.base import DatabaseConnector
from src.connectors.common import apply_key_flags, new_column, new_object
from src.connectors.object_metadata import normalize_object_metadata

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
        """Discover Oracle tables, views, routines, and triggers."""

        owner = (
            self.config.get("schema_name")
            or self.config["username"]
        ).upper()

        query = """
            SELECT
                object_info.OWNER,
                object_info.OBJECT_NAME,
                object_info.OBJECT_TYPE,
                object_info.CREATED,
                object_info.LAST_DDL_TIME,
                object_info.STATUS
            FROM ALL_OBJECTS object_info
            WHERE object_info.OWNER = :owner
              AND object_info.OBJECT_TYPE IN (
                  'TABLE',
                  'VIEW',
                  'MATERIALIZED VIEW',
                  'PROCEDURE',
                  'FUNCTION'
              )
            ORDER BY
                object_info.OBJECT_TYPE,
                object_info.OBJECT_NAME
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

        objects: list[dict[str, Any]] = []

        for row in rows:
            schema_name = str(row[0])
            object_name = str(row[1])
            source_type = str(row[2])
            created_at = row[3]
            last_ddl_time = row[4]
            status = str(row[5] or "").upper()

            object_type = type_map.get(
                source_type,
                source_type,
            )

            object_ddl = self._get_object_ddl(
                schema_name=schema_name,
                object_name=object_name,
                object_type=object_type,
            )

            routine_metadata = {}

            if object_type in {
                "PROCEDURE",
                "FUNCTION",
            }:
                routine_metadata = self._routine_metadata(
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
                    "source_object_type": source_type,
                    "created_at": created_at,
                    "last_altered_at": last_ddl_time,
                    "enabled": status == "VALID",
                    "materialized": (
                        object_type == "MATERIALIZED_VIEW"
                    ),
                    **routine_metadata,
                },
            )

            if object_type in {
                "TABLE",
                "VIEW",
                "MATERIALIZED_VIEW",
            }:
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
            self._discover_triggers(owner)
        )

        return objects
    
    def _discover_triggers(
        self,
        owner: str,
    ) -> list[dict[str, Any]]:
        """Discover Oracle triggers accessible to the source user."""

        query = """
            SELECT
                trigger_info.OWNER,
                trigger_info.TRIGGER_NAME,
                trigger_info.TRIGGER_TYPE,
                trigger_info.TRIGGERING_EVENT,
                trigger_info.TABLE_OWNER,
                trigger_info.TABLE_NAME,
                trigger_info.BASE_OBJECT_TYPE,
                trigger_info.STATUS,
                trigger_info.DESCRIPTION,
                trigger_info.ACTION_TYPE,
                trigger_info.TRIGGER_BODY,
                trigger_info.WHEN_CLAUSE,
                object_info.CREATED,
                object_info.LAST_DDL_TIME
            FROM ALL_TRIGGERS trigger_info

            LEFT JOIN ALL_OBJECTS object_info
              ON object_info.OWNER =
                 trigger_info.OWNER
             AND object_info.OBJECT_NAME =
                 trigger_info.TRIGGER_NAME
             AND object_info.OBJECT_TYPE =
                 'TRIGGER'

            WHERE trigger_info.OWNER = :owner

            ORDER BY
                trigger_info.OWNER,
                trigger_info.TRIGGER_NAME
        """

        cursor = self.connection.cursor()

        try:
            cursor.execute(
                query,
                owner=owner,
            )
            rows = cursor.fetchall()
        finally:
            cursor.close()

        triggers: list[dict[str, Any]] = []

        for row in rows:
            trigger_owner = str(row[0])
            trigger_name = str(row[1])
            trigger_type = str(row[2] or "")
            triggering_event = str(row[3] or "")
            table_owner = (
                str(row[4])
                if row[4] is not None
                else None
            )
            table_name = (
                str(row[5])
                if row[5] is not None
                else None
            )
            base_object_type = (
                str(row[6])
                if row[6] is not None
                else None
            )
            status = str(row[7] or "").upper()
            description = (
                str(row[8])
                if row[8] is not None
                else None
            )
            action_type = (
                str(row[9])
                if row[9] is not None
                else None
            )
            trigger_body = (
                str(row[10])
                if row[10] is not None
                else None
            )
            when_clause = (
                str(row[11])
                if row[11] is not None
                else None
            )
            created_at = row[12]
            last_ddl_time = row[13]

            trigger_ddl = self._get_object_ddl(
                schema_name=trigger_owner,
                object_name=trigger_name,
                object_type="TRIGGER",
            )

            if not trigger_ddl:
                trigger_ddl = (
                    self._build_trigger_definition(
                        description=description,
                        trigger_body=trigger_body,
                    )
                )

            trigger_details = (
                self._parse_trigger_properties(
                    trigger_type=trigger_type,
                    triggering_event=triggering_event,
                )
            )

            trigger = new_object(
                schema_name=trigger_owner,
                object_name=trigger_name,
                object_type="TRIGGER",
                object_ddl=trigger_ddl,
                metadata={
                    "language": (
                        "PLSQL"
                        if action_type == "PL/SQL"
                        else action_type
                    ),
                    "parameter_count": 0,
                    "created_at": created_at,
                    "last_altered_at": last_ddl_time,
                    "return_type": None,
                    "materialized": False,
                    "enabled": status == "ENABLED",
                    "status": status,
                    "trigger_table_schema": table_owner,
                    "trigger_table": table_name,
                    "base_object_type": base_object_type,
                    "trigger_type": trigger_type,
                    "trigger_timing": (
                        trigger_details["timing"]
                    ),
                    "trigger_events": (
                        trigger_details["events"]
                    ),
                    "orientation": (
                        trigger_details["orientation"]
                    ),
                    "action_type": action_type,
                    "when_clause": when_clause,
                    "description": description,
                },
            )

            triggers.append(trigger)

        return triggers
    
    @staticmethod
    def _parse_trigger_properties(
        trigger_type: str,
        triggering_event: str,
    ) -> dict[str, Any]:
        """Normalize Oracle trigger timing, events, and orientation."""

        normalized_type = str(
            trigger_type or ""
        ).strip().upper()

        normalized_event = str(
            triggering_event or ""
        ).strip().upper()

        timing = None

        if normalized_type.startswith("BEFORE"):
            timing = "BEFORE"
        elif normalized_type.startswith("AFTER"):
            timing = "AFTER"
        elif normalized_type.startswith("INSTEAD OF"):
            timing = "INSTEAD OF"
        elif "COMPOUND" in normalized_type:
            timing = "COMPOUND"

        orientation = None

        if "EACH ROW" in normalized_type:
            orientation = "ROW"
        elif "STATEMENT" in normalized_type:
            orientation = "STATEMENT"
        elif "INSTEAD OF" in normalized_type:
            orientation = "ROW"
        elif "COMPOUND" in normalized_type:
            orientation = "COMPOUND"

        events = []

        for event_part in normalized_event.split(" OR "):
            event_name = event_part.strip()

            if (
                event_name
                and event_name not in events
            ):
                events.append(event_name)

        return {
            "timing": timing,
            "events": events,
            "orientation": orientation,
        }
    
    @staticmethod
    def _build_trigger_definition(
        description: str | None,
        trigger_body: str | None,
    ) -> str | None:
        """
        Build a readable trigger definition when
        DBMS_METADATA.GET_DDL is unavailable.
        """

        definition_parts: list[str] = []

        if description:
            cleaned_description = str(
                description
            ).strip()

            if cleaned_description:
                if cleaned_description.upper().startswith(
                    "CREATE"
                ):
                    definition_parts.append(
                        cleaned_description
                    )
                else:
                    definition_parts.append(
                        "CREATE OR REPLACE TRIGGER "
                        + cleaned_description
                    )

        if trigger_body:
            cleaned_body = str(
                trigger_body
            ).strip()

            if cleaned_body:
                definition_parts.append(
                    cleaned_body
                )

        if not definition_parts:
            return None

        return "\n".join(definition_parts)
         
    def _get_object_ddl(
        self,
        schema_name: str,
        object_name: str,
        object_type: str,
    ) -> str | None:
        """Get complete Oracle object DDL using DBMS_METADATA."""

        ddl_type_map = {
            "TABLE": "TABLE",
            "VIEW": "VIEW",
            "MATERIALIZED_VIEW": "MATERIALIZED_VIEW",
            "PROCEDURE": "PROCEDURE",
            "FUNCTION": "FUNCTION",
            "TRIGGER": "TRIGGER",
        }

        ddl_type = ddl_type_map.get(
            object_type
        )

        if ddl_type is None:
            return None

        query = """
            SELECT DBMS_METADATA.GET_DDL(
                :ddl_type,
                :object_name,
                :schema_name
            )
            FROM DUAL
        """

        cursor = self.connection.cursor()

        try:
            cursor.execute(
                query,
                ddl_type=ddl_type,
                object_name=object_name,
                schema_name=schema_name,
            )

            row = cursor.fetchone()
        except Exception:
            return None
        finally:
            cursor.close()

        if row is None or row[0] is None:
            return None

        ddl_value = row[0]

        if hasattr(ddl_value, "read"):
            ddl_value = ddl_value.read()

        return str(ddl_value)
    
    def _routine_metadata(
        self,
        schema_name: str,
        object_name: str,
        object_type: str,
    ) -> dict[str, Any]:
        """Return Oracle routine language, parameters, and return type."""

        parameter_query = """
            SELECT COUNT(*)
            FROM ALL_ARGUMENTS
            WHERE OWNER = :owner
              AND OBJECT_NAME = :object_name
              AND PACKAGE_NAME IS NULL
              AND POSITION > 0
        """

        return_type_query = """
            SELECT DATA_TYPE
            FROM ALL_ARGUMENTS
            WHERE OWNER = :owner
              AND OBJECT_NAME = :object_name
              AND PACKAGE_NAME IS NULL
              AND POSITION = 0
              AND ROWNUM = 1
        """

        cursor = self.connection.cursor()

        try:
            cursor.execute(
                parameter_query,
                owner=schema_name,
                object_name=object_name,
            )

            parameter_row = cursor.fetchone()

            parameter_count = (
                int(parameter_row[0])
                if parameter_row
                else 0
            )

            return_type = None

            if object_type == "FUNCTION":
                cursor.execute(
                    return_type_query,
                    owner=schema_name,
                    object_name=object_name,
                )

                return_row = cursor.fetchone()

                if (
                    return_row
                    and return_row[0] is not None
                ):
                    return_type = str(
                        return_row[0]
                    )
        finally:
            cursor.close()

        return {
            "language": "PLSQL",
            "parameter_count": parameter_count,
            "return_type": return_type,
            "materialized": False,
        }
        
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
