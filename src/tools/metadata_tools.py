from __future__ import annotations

from typing import Any


SYSTEM_SCHEMAS = {
    "information_schema",
    "pg_catalog",
    "pg_toast",
}


def discover_database_metadata(
    source_connection: Any,
) -> list[dict]:
    """
    Discover PostgreSQL tables, views, columns, primary keys,
    and foreign keys.

    The supplied source connection must be a psycopg connection.
    This function performs read-only catalog queries.

    Returns:
    f dictionaries. Each dictionary represents one
        discovered table or view.
    """

    objects = _discover_objects(source_connection)

    for database_object in objects:
        schema_name = database_object["schema_name"]
        object_name = database_object["object_name"]

        columns = _discover_columns(
            source_connection=source_connection,
            schema_name=schema_name,
            object_name=object_name,
        )

        database_object["columns"] = columns

        if database_object["object_type"] == "TABLE":
            primary_key_columns = _discover_primary_keys(
                source_connection=source_connection,
                schema_name=schema_name,
                table_name=object_name,
            )

            foreign_keys = _discover_foreign_keys(
                source_connection=source_connection,
                schema_name=schema_name,
                table_name=object_name,
            )

            database_object["primary_key_columns"] = primary_key_columns
            database_object["foreign_keys"] = foreign_keys

            _apply_key_flags(
                columns=columns,
                primary_key_columns=primary_key_columns,
                foreign_keys=foreign_keys,
            )
        else:
            database_object["primary_key_columns"] = []
            database_object["foreign_keys"] = []

    return objects


def _discover_objects(
    source_connection: Any,
) -> list[dict]:
    """
    Discover user-created PostgreSQL tables and views.

    System schemas such as pg_catalog and information_schema
    are excluded.
    """

    query = """
        SELECT
            table_schema,
            table_name,
            table_type
        FROM information_schema.tables
        WHERE table_schema NOT IN (
            'information_schema',
            'pg_catalog',
            'pg_toast'
        )
          AND table_schema NOT LIKE 'pg_temp_%'
          AND table_schema NOT LIKE 'pg_toast_temp_%'
          AND table_type IN ('BASE TABLE', 'VIEW')
        ORDER BY
            table_schema,
            table_name;
    """

    with source_connection.cursor() as cursor:
        cursor.execute(query)
        rows = cursor.fetchall()

    objects: list[dict] = []

    for table_schema, table_name, table_type in rows:
        object_type = (
            "TABLE"
            if table_type == "BASE TABLE"
            else "VIEW"
        )

        objects.append(
            {
                "schema_name": table_schema,
                "object_name": table_name,
                "object_type": object_type,
                "object_ddl": None,
                "object_metadata": {
                    "source_table_type": table_type,
                },
                "columns": [],
                "primary_key_columns": [],
                "foreign_keys": [],
            }
        )

    return objects


def _discover_columns(
    source_connection: Any,
    schema_name: str,
    object_name: str,
) -> list[dict]:
    """
    Discover columns belonging to one PostgreSQL table or view.
    """

    query = """
        SELECT
            column_name,
            ordinal_position,
            data_type,
            udt_name,
            is_nullable,
            column_default,
            character_maximum_length,
            numeric_precision,
            numeric_scale
        FROM information_schema.columns
        WHERE table_schema = %s
          AND table_name = %s
        ORDER BY ordinal_position;
    """

    with source_connection.cursor() as cursor:
        cursor.execute(
            query,
            (
                schema_name,
                object_name,
            ),
        )
        rows = cursor.fetchall()

    columns: list[dict] = []

    for row in rows:
        (
            column_name,
            ordinal_position,
            data_type,
            udt_name,
            is_nullable,
            column_default,
            character_maximum_length,
            numeric_precision,
            numeric_scale,
        ) = row

        formatted_data_type = _format_data_type(
            data_type=data_type,
            character_maximum_length=character_maximum_length,
            numeric_precision=numeric_precision,
            numeric_scale=numeric_scale,
        )

        columns.append(
            {
                "column_name": column_name,
                "ordinal_position": ordinal_position,
                "data_type": formatted_data_type,
                "native_data_type": udt_name,
                "nullable": is_nullable == "YES",
                "default_value": column_default,
                "is_primary_key": False,
                "is_foreign_key": False,
                "column_metadata": {},
            }
        )

    return columns


def _discover_primary_keys(
    source_connection: Any,
    schema_name: str,
    table_name: str,
) -> list[str]:
    """
    Return the column names forming the table's primary key.
    """

    query = """
        SELECT
            key_column_usage.column_name
        FROM information_schema.table_constraints
        JOIN information_schema.key_column_usage
          ON table_constraints.constraint_name =
             key_column_usage.constraint_name
         AND table_constraints.constraint_schema =
             key_column_usage.constraint_schema
         AND table_constraints.table_name =
             key_column_usage.table_name
        WHERE table_constraints.constraint_type = 'PRIMARY KEY'
          AND table_constraints.table_schema = %s
          AND table_constraints.table_name = %s
        ORDER BY key_column_usage.ordinal_position;
    """

    with source_connection.cursor() as cursor:
        cursor.execute(
            query,
            (
                schema_name,
                table_name,
            ),
        )
        rows = cursor.fetchall()

    return [row[0] for row in rows]


def _discover_foreign_keys(
    source_connection: Any,
    schema_name: str,
    table_name: str,
) -> list[dict]:
    """
    Return foreign-key relationships for one PostgreSQL table.
    """

    query = """
        SELECT
            source_usage.constraint_name,
            source_usage.column_name AS source_column,
            target_usage.table_schema AS target_schema,
            target_usage.table_name AS target_table,
            target_usage.column_name AS target_column
        FROM information_schema.table_constraints AS constraints
        JOIN information_schema.key_column_usage AS source_usage
          ON constraints.constraint_name =
             source_usage.constraint_name
         AND constraints.constraint_schema =
             source_usage.constraint_schema
        JOIN information_schema.constraint_column_usage AS target_usage
          ON constraints.constraint_name =
             target_usage.constraint_name
         AND constraints.constraint_schema =
             target_usage.constraint_schema
        WHERE constraints.constraint_type = 'FOREIGN KEY'
          AND constraints.table_schema = %s
          AND constraints.table_name = %s
        ORDER BY
            source_usage.constraint_name,
            source_usage.ordinal_position;
    """

    with source_connection.cursor() as cursor:
        cursor.execute(
            query,
            (
                schema_name,
                table_name,
            ),
        )
        rows = cursor.fetchall()

    foreign_keys: list[dict] = []

    for (
        constraint_name,
        source_column,
        target_schema,
        target_table,
        target_column,
    ) in rows:
        foreign_keys.append(
            {
                "constraint_name": constraint_name,
                "source_schema": schema_name,
                "source_table": table_name,
                "source_column": source_column,
                "target_schema": target_schema,
                "target_table": target_table,
                "target_column": target_column,
            }
        )

    return foreign_keys


def _apply_key_flags(
    columns: list[dict],
    primary_key_columns: list[str],
    foreign_keys: list[dict],
) -> None:
    """
    Update column dictionaries with primary-key and foreign-key flags.
    """

    primary_key_set = set(primary_key_columns)

    foreign_key_set = {
        foreign_key["source_column"]
        for foreign_key in foreign_keys
    }

    for column in columns:
        column_name = column["column_name"]

        column["is_primary_key"] = (
            column_name in primary_key_set
        )

        column["is_foreign_key"] = (
            column_name in foreign_key_set
        )


def _format_data_type(
    data_type: str,
    character_maximum_length: int | None,
    numeric_precision: int | None,
    numeric_scale: int | None,
) -> str:
    """
    Produce a readable data type such as VARCHAR(100)
    or NUMERIC(10,2).
    """

    if (
        data_type in {"character varying", "character"}
        and character_maximum_length is not None
    ):
        readable_name = (
            "VARCHAR"
            if data_type == "character varying"
            else "CHAR"
        )

        return (
            f"{readable_name}"
            f"({character_maximum_length})"
        )

    if (
        data_type == "numeric"
        and numeric_precision is not None
    ):
        if numeric_scale is not None:
            return (
                f"NUMERIC"
                f"({numeric_precision},{numeric_scale})"
            )

        return f"NUMERIC({numeric_precision})"

    data_type_names = {
        "integer": "INTEGER",
        "bigint": "BIGINT",
        "smallint": "SMALLINT",
        "boolean": "BOOLEAN",
        "text": "TEXT",
        "date": "DATE",
        "time without time zone": "TIME",
        "time with time zone": "TIMETZ",
        "timestamp without time zone": "TIMESTAMP",
        "timestamp with time zone": "TIMESTAMPTZ",
        "double precision": "DOUBLE PRECISION",
        "real": "REAL",
        "uuid": "UUID",
        "json": "JSON",
        "jsonb": "JSONB",
        "bytea": "BYTEA",
        "array": "ARRAY",
        "user-defined": "USER-DEFINED",
    }

    return data_type_names.get(
        data_type,
        data_type.upper(),
    )


def persist_discovered_metadata(
    run_id: str,
    objects: list[dict],
) -> None:
    """
    Persist discovered objects and columns.

    This will be implemented after metadata discovery has been
    independently tested. Persistence requires the metadata
    database connection and the connection ID.
    """

    raise NotImplementedError(
        "Metadata persistence will be implemented after "
        "PostgreSQL metadata discovery is tested."
    )