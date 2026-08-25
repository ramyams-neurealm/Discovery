from __future__ import annotations

import re
from typing import Any


MAX_SAMPLE_VALUES = 3
_VALID_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_$#]*$")


def profile_tables(source_connector: Any, objects: list[dict[str, Any]]):
    """Profile tables through a PostgreSQL, MySQL, SQL Server, or Oracle connector."""
    table_profiles = []
    column_profiles = []

    for database_object in objects:
        if database_object.get("object_type") != "TABLE":
            continue

        schema_name = database_object["schema_name"]
        table_name = database_object["object_name"]
        columns = database_object.get("columns", [])

        row_count = _scalar(
            source_connector,
            _row_count_query(source_connector, schema_name, table_name),
        )

        current_profiles = []
        for column in columns:
            profile = _profile_column(
                source_connector=source_connector,
                schema_name=schema_name,
                table_name=table_name,
                row_count=row_count,
                column=column,
                all_columns=columns,
            )
            current_profiles.append(profile)
            column_profiles.append(profile)

        percentages = [
            profile["null_percentage"]
            for profile in current_profiles
            if profile.get("null_percentage") is not None
        ]
        average_null = (
            round(sum(percentages) / len(percentages), 4)
            if percentages
            else 0.0
        )

        table_profiles.append(
            {
                "object_id": database_object["object_id"],
                "schema_name": schema_name,
                "table_name": table_name,
                "row_count": row_count,
                "column_count": len(columns),
                "average_null_percentage": average_null,
                "profiling_method": "EXACT",
                "profile_metadata": {
                    "database_vendor": _vendor(source_connector),
                },
            }
        )

    return table_profiles, column_profiles


def _profile_column(
    source_connector: Any,
    schema_name: str,
    table_name: str,
    row_count: int,
    column: dict[str, Any],
    all_columns: list[dict[str, Any]],
):
    column_name = column["column_name"]
    table_ref = _table_reference(source_connector, schema_name, table_name)
    column_ref = _quote_identifier(source_connector, column_name)
    distinct_column_ref = _distinct_expression(
        source_connector=source_connector,
        column=column,
        column_ref=column_ref,
    )
    null_count = _scalar(
        source_connector,
        f"SELECT COUNT(*) FROM {table_ref} WHERE {column_ref} IS NULL",
    )
    distinct_count = _scalar(
        source_connector,
        (
            f"SELECT COUNT(DISTINCT {distinct_column_ref}) "
            f"FROM {table_ref} "
            f"WHERE {column_ref} IS NOT NULL"
        ),
    )
    raw_samples = _sample_values(
        source_connector=source_connector,
        table_ref=table_ref,
        column_ref=column_ref,
        sample_expression=distinct_column_ref,
    )

    null_percentage = (
        0.0
        if row_count == 0
        else round((null_count / row_count) * 100, 4)
    )
    masked_samples = [mask_sample(value) for value in raw_samples]

    return {
        "column_id": column["column_id"],
        "object_id": column["object_id"],
        "schema_name": schema_name,
        "table_name": table_name,
        "column_name": column_name,
        "data_type": column["data_type"],
        "nullable": column.get("nullable"),
        "is_primary_key": column.get("is_primary_key", False),
        "is_foreign_key": column.get("is_foreign_key", False),
        "neighboring_columns": _neighboring_columns(column, all_columns),
        "null_percentage": null_percentage,
        "distinct_count": distinct_count,
        "distinct_count_is_approximate": False,
        "masked_samples": masked_samples,
        "profile_metadata": {
            "null_count": null_count,
            "sample_count": len(masked_samples),
            "database_vendor": _vendor(source_connector),
        },
    }


def _row_count_query(source_connector: Any, schema_name: str, table_name: str):
    return f"SELECT COUNT(*) FROM {_table_reference(source_connector, schema_name, table_name)}"

def _distinct_expression(
    source_connector: Any,
    column: dict[str, Any],
    column_ref: str,
) -> str:
    """
    Return a SQL expression that supports DISTINCT operations.

    PostgreSQL JSON has no equality operator, so JSON values are
    converted to text for distinct counting and sample selection.
    """

    vendor = _vendor(source_connector)

    native_data_type = str(
        column.get("native_data_type")
        or column.get("data_type")
        or ""
    ).strip().lower()

    if (
        vendor == "POSTGRESQL"
        and native_data_type == "json"
    ):
        return f"CAST({column_ref} AS TEXT)"

    return column_ref

def _sample_values(
    source_connector: Any,
    table_ref: str,
    column_ref: str,
    sample_expression: str,
):
    """
    Return distinct non-null sample values.

    sample_expression may differ from column_ref for source types
    that do not support equality, such as PostgreSQL JSON.
    """

    vendor = _vendor(source_connector)

    if vendor == "SQL_SERVER":
        query = (
            f"SELECT DISTINCT TOP {MAX_SAMPLE_VALUES} "
            f"{sample_expression} "
            f"FROM {table_ref} "
            f"WHERE {column_ref} IS NOT NULL"
        )

    elif vendor == "ORACLE":
        query = (
            f"SELECT DISTINCT {sample_expression} "
            f"FROM {table_ref} "
            f"WHERE {column_ref} IS NOT NULL "
            f"FETCH FIRST {MAX_SAMPLE_VALUES} ROWS ONLY"
        )

    else:
        query = (
            f"SELECT DISTINCT {sample_expression} "
            f"FROM {table_ref} "
            f"WHERE {column_ref} IS NOT NULL "
            f"LIMIT {MAX_SAMPLE_VALUES}"
        )

    cursor = source_connector.connection.cursor()

    try:
        cursor.execute(query)
        rows = cursor.fetchall()
    finally:
        cursor.close()

    return [row[0] for row in rows]


def _scalar(source_connector: Any, query: str):
    cursor = source_connector.connection.cursor()
    try:
        cursor.execute(query)
        row = cursor.fetchone()
    finally:
        cursor.close()
    return int(row[0]) if row else 0


def _vendor(source_connector: Any):
    class_name = source_connector.__class__.__name__
    mapping = {
        "PostgreSQLConnector": "POSTGRESQL",
        "MySQLConnector": "MYSQL",
        "SQLServerConnector": "SQL_SERVER",
        "OracleConnector": "ORACLE",
    }
    vendor = mapping.get(class_name)
    if vendor is None:
        raise ValueError(f"Unsupported connector class: {class_name}")
    return vendor


def _table_reference(source_connector: Any, schema_name: str, table_name: str):
    return (
        f"{_quote_identifier(source_connector, schema_name)}."
        f"{_quote_identifier(source_connector, table_name)}"
    )


def _quote_identifier(source_connector: Any, identifier: str):
    """Quote a database identifier safely, including names with spaces."""
    if not isinstance(identifier, str) or not identifier:
        raise ValueError("Database identifier must be a non-empty string")

    if "\x00" in identifier:
        raise ValueError("Database identifier contains a null character")

    vendor = _vendor(source_connector)

    if vendor == "MYSQL":
        escaped = identifier.replace("`", "``")
        return f"`{escaped}`"

    if vendor == "SQL_SERVER":
        escaped = identifier.replace("]", "]]" )
        return f"[{escaped}]"

    escaped = identifier.replace('"', '""')
    return f'"{escaped}"'


def _neighboring_columns(column, all_columns):
    selected_position = column.get("ordinal_position")
    if selected_position is None:
        return []

    neighbors = []
    for candidate in all_columns:
        position = candidate.get("ordinal_position")
        name = candidate.get("column_name")
        if position is None or name is None:
            continue
        if name == column.get("column_name"):
            continue
        if abs(position - selected_position) <= 2:
            neighbors.append(name)
    return neighbors


def mask_sample(value: Any, classification=None):
    """Mask values before persistence or classification."""
    del classification
    if value is None:
        return ""
    text = str(value)
    if not text:
        return ""
    if len(text) <= 2:
        return "*" * len(text)
    return text[0] + "*" * (len(text) - 2) + text[-1]
