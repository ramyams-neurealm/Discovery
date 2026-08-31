from __future__ import annotations

from datetime import date, datetime
from typing import Any


VALID_COMPLEXITY_LEVELS = {
    "LOW",
    "MEDIUM",
    "HIGH",
}


def normalize_object_metadata(
    metadata: dict[str, Any] | None,
    object_ddl: str | None,
    object_type: str,
    column_count: int = 0,
    foreign_key_count: int = 0,
    dependency_count: int = 0,
) -> dict[str, Any]:
    """Return a consistent metadata structure for every object type."""
    normalized = dict(metadata or {})
    normalized_type = str(object_type).strip().upper()

    normalized["language"] = _optional_text(
        normalized.get("language")
    )
    normalized["parameter_count"] = _non_negative_int(
        normalized.get("parameter_count")
    )
    normalized["lines_of_code"] = _non_negative_int(
        normalized.get("lines_of_code"),
        default=count_lines(object_ddl),
    )
    normalized["last_altered_at"] = serialize_datetime(
        normalized.get("last_altered_at")
    )
    normalized["return_type"] = _optional_text(
        normalized.get("return_type")
    )
    normalized["materialized"] = bool(
        normalized.get("materialized", False)
    )
    normalized["enabled"] = bool(
        normalized.get("enabled", True)
    )

    normalized["column_count"] = _non_negative_int(
        column_count
    )
    normalized["foreign_key_count"] = _non_negative_int(
        foreign_key_count
    )
    normalized["dependency_count"] = _non_negative_int(
        dependency_count
    )

    normalized["complexity"] = calculate_complexity(
        object_type=normalized_type,
        lines_of_code=normalized["lines_of_code"],
        parameter_count=normalized["parameter_count"],
        column_count=normalized["column_count"],
        foreign_key_count=normalized["foreign_key_count"],
        dependency_count=normalized["dependency_count"],
    )

    return _json_safe(normalized)


def count_lines(object_ddl: str | None) -> int:
    """Count non-empty lines in an object's SQL definition."""
    if not object_ddl:
        return 0

    return sum(
        1
        for line in str(object_ddl).splitlines()
        if line.strip()
    )


def serialize_datetime(value: Any) -> str | None:
    """Convert date-like catalog values into JSON-safe ISO text."""
    if value is None:
        return None

    if isinstance(value, (datetime, date)):
        return value.isoformat()

    text = str(value).strip()
    return text or None


def calculate_complexity(
    object_type: str,
    lines_of_code: int = 0,
    parameter_count: int = 0,
    column_count: int = 0,
    foreign_key_count: int = 0,
    dependency_count: int = 0,
) -> str:
    """Calculate a deterministic LOW, MEDIUM, or HIGH rating."""
    normalized_type = str(object_type).strip().upper()

    if normalized_type == "TABLE":
        score = (
            _non_negative_int(column_count)
            + (_non_negative_int(foreign_key_count) * 3)
        )
    else:
        score = (
            _non_negative_int(lines_of_code)
            + (_non_negative_int(parameter_count) * 5)
            + (_non_negative_int(dependency_count) * 15)
        )

    if score >= 110:
        return "HIGH"

    if score >= 45:
        return "MEDIUM"

    return "LOW"


def _non_negative_int(
    value: Any,
    default: int = 0,
) -> int:
    if value is None or value == "":
        return max(0, int(default))

    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return max(0, int(default))


def _optional_text(value: Any) -> str | None:
    if value is None:
        return None

    text = str(value).strip()
    return text or None


def _json_safe(value: Any) -> Any:
    """Recursively convert common catalog values to JSON-safe values."""
    if isinstance(value, dict):
        return {
            str(key): _json_safe(item)
            for key, item in value.items()
        }

    if isinstance(value, (list, tuple, set)):
        return [_json_safe(item) for item in value]

    if isinstance(value, (datetime, date)):
        return value.isoformat()

    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")

    return value
