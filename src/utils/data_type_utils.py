from __future__ import annotations

from typing import Any


NUMERIC_DATA_TYPES = frozenset({
    "BIGINT",
    "BIGSERIAL",
    "BINARY_DOUBLE",
    "BINARY_FLOAT",
    "DEC",
    "DECIMAL",
    "DOUBLE",
    "DOUBLE PRECISION",
    "FLOAT",
    "INT",
    "INTEGER",
    "MEDIUMINT",
    "MONEY",
    "NUMBER",
    "NUMERIC",
    "REAL",
    "SERIAL",
    "SMALLINT",
    "SMALLMONEY",
    "SMALLSERIAL",
    "TINYINT",
})

TEXT_DATA_TYPES = frozenset({
    "BIT",
    "BOOL",
    "BOOLEAN",
    "CHAR",
    "CHARACTER",
    "CHARACTER VARYING",
    "CLOB",
    "ENUM",
    "LONGTEXT",
    "MEDIUMTEXT",
    "NCHAR",
    "NCLOB",
    "NTEXT",
    "NVARCHAR",
    "NVARCHAR2",
    "SET",
    "TEXT",
    "TINYTEXT",
    "VARCHAR",
    "VARCHAR2",
})

OTHER_DATA_TYPES = frozenset({
    "ARRAY",
    "BFILE",
    "BINARY",
    "BLOB",
    "BYTEA",
    "DATE",
    "DATETIME",
    "DATETIME2",
    "DATETIMEOFFSET",
    "GEOGRAPHY",
    "GEOMETRY",
    "IMAGE",
    "INTERVAL",
    "JSON",
    "JSONB",
    "LONG RAW",
    "RAW",
    "SMALLDATETIME",
    "TIME",
    "TIMESTAMP",
    "TIMESTAMP WITH LOCAL TIME ZONE",
    "TIMESTAMP WITH TIME ZONE",
    "TIMESTAMP WITHOUT TIME ZONE",
    "UUID",
    "VARBINARY",
    "XML",
})


def classify_data_type(data_type: Any) -> str:
    """
    Classify a normalized SQL type.

    Unknown and user-defined types safely return OTHER.
    """
    normalized_type = str(data_type or "").strip().upper()
    base_type = normalized_type.split("(", 1)[0].strip()

    if base_type in NUMERIC_DATA_TYPES:
        return "NUMERIC"

    if base_type in TEXT_DATA_TYPES:
        return "CATEGORICAL"

    if base_type in OTHER_DATA_TYPES:
        return "OTHER"

    return "OTHER"