from __future__ import annotations

from typing import Any


SYSTEM_SCHEMAS = {
    "information_schema",
    "pg_catalog",
    "pg_toast",
    "mysql",
    "performance_schema",
    "sys",
}


def new_object(
    schema_name: str,
    object_name: str,
    object_type: str,
    object_ddl: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "schema_name": schema_name,
        "object_name": object_name,
        "object_type": object_type,
        "object_ddl": object_ddl,
        "object_metadata": metadata or {},
        "columns": [],
        "primary_key_columns": [],
        "foreign_keys": [],
    }


def new_column(
    column_name: str,
    ordinal_position: int | None,
    data_type: str,
    nullable: bool | None,
    default_value: Any = None,
    native_data_type: str | None = None,
) -> dict[str, Any]:
    return {
        "column_name": column_name,
        "ordinal_position": ordinal_position,
        "data_type": data_type,
        "native_data_type": native_data_type or data_type,
        "nullable": nullable,
        "default_value": None if default_value is None else str(default_value),
        "is_primary_key": False,
        "is_foreign_key": False,
        "column_metadata": {},
    }


def apply_key_flags(database_object: dict[str, Any]) -> None:
    primary_keys = set(database_object.get("primary_key_columns", []))
    foreign_keys = {
        item["source_column"]
        for item in database_object.get("foreign_keys", [])
    }
    for column in database_object.get("columns", []):
        name = column["column_name"]
        column["is_primary_key"] = name in primary_keys
        column["is_foreign_key"] = name in foreign_keys
