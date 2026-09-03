from __future__ import annotations

import re
from typing import Any

from src.models.schemas import DependencyEdge


SUPPORTED_DEFINITION_OBJECT_TYPES = {
    "VIEW",
    "MATERIALIZED_VIEW",
    "PROCEDURE",
    "FUNCTION",
    "TRIGGER",
}


def extract_catalog_dependencies(
    objects: list[dict[str, Any]],
) -> list: 
    """Create deterministic dependency edges from foreign-key metadata."""

    edges: list[DependencyEdge] = []

    for database_object in objects:
        if database_object.get("object_type") != "TABLE":
            continue

        source_name = _qualified_name(
            database_object["schema_name"],
            database_object["object_name"],
        )

        for foreign_key in database_object.get(
            "foreign_keys",
            [],
        ):
            target_name = _qualified_name(
                foreign_key["target_schema"],
                foreign_key["target_table"],
            )

            edges.append(
                DependencyEdge(
                    source_object=source_name,
                    source_object_type="TABLE",
                    target_object=target_name,
                    target_object_type="TABLE",
                    relationship_type="FOREIGN_KEY",
                    source_column=foreign_key.get(
                        "source_column"
                    ),
                    target_column=foreign_key.get(
                        "target_column"
                    ),
                    evidence_source="SOURCE_CATALOG",
                    confidence=1.0,
                )
            )

    return edges


def parse_definition_dependencies(
    objects: list[dict[str, Any]],
) -> list:
    """Extract READS, WRITES, and CALLS relationships from object DDL.

    SQL-definition parsing is conservative. Ambiguous references are
    skipped rather than linked to an uncertain target.
    """

    catalog = {
        _qualified_name(
            item["schema_name"],
            item["object_name"],
        ).lower(): item
        for item in objects
    }

    short_name_index: dict[
        str,
        list[dict[str, Any]],
    ] = {}

    for item in objects:
        short_name = str(
            item["object_name"]
        ).lower()

        short_name_index.setdefault(
            short_name,
            [],
        ).append(item)

    edges: list[DependencyEdge] = []

    seen: set[
        tuple[str, str, str]
    ] = set()

    for source in objects:
        source_type = str(
            source.get("object_type") or ""
        ).upper()

        if (
            source_type
            not in SUPPORTED_DEFINITION_OBJECT_TYPES
        ):
            continue

        definition = str(
            source.get("object_ddl") or ""
        )

        if not definition.strip():
            continue

        source_schema = str(
            source["schema_name"]
        )

        source_name = _qualified_name(
            source_schema,
            source["object_name"],
        )

        cleaned_definition = _remove_sql_comments(
            definition
        )

        references = _extract_definition_references(
            cleaned_definition
        )

        for reference in references:
            token = reference["token"]
            relationship_type = reference[
                "relationship_type"
            ]

            target, confidence = _resolve_object(
                token=token,
                source_schema=source_schema,
                catalog=catalog,
                short_name_index=short_name_index,
                relationship_type=relationship_type,
            )

            if target is None:
                continue

            target_name = _qualified_name(
                target["schema_name"],
                target["object_name"],
            )

            if source_name.lower() == target_name.lower():
                continue

            key = (
                source_name.lower(),
                target_name.lower(),
                relationship_type,
            )

            if key in seen:
                continue

            seen.add(key)

            edges.append(
                DependencyEdge(
                    source_object=source_name,
                    source_object_type=source_type,
                    target_object=target_name,
                    target_object_type=str(
                        target["object_type"]
                    ).upper(),
                    relationship_type=relationship_type,
                    source_column=None,
                    target_column=None,
                    evidence_source=(
                        _evidence_source(
                            source_type
                        )
                    ),
                    confidence=confidence,
                )
            )

    return edges


def _extract_definition_references(
    definition: str,
) -> list[dict[str, str]]:
    """
    Return normalized read, write, and call references from SQL text.

    Write targets are masked before read extraction so DELETE FROM does
    not incorrectly create both WRITES and READS edges for the target.
    """

    references: list[dict[str, str]] = []
    masked_definition = definition

    write_patterns = (
        (
            "WRITES",
            re.compile(
                rf"\bINSERT\s+INTO\s+"
                rf"({_identifier_pattern()})",
                flags=re.IGNORECASE,
            ),
        ),
        (
            "WRITES",
            re.compile(
                rf"\bUPDATE\s+"
                rf"({_identifier_pattern()})",
                flags=re.IGNORECASE,
            ),
        ),
        (
            "WRITES",
            re.compile(
                rf"\bDELETE\s+FROM\s+"
                rf"({_identifier_pattern()})",
                flags=re.IGNORECASE,
            ),
        ),
        (
            "WRITES",
            re.compile(
                rf"\bMERGE\s+INTO\s+"
                rf"({_identifier_pattern()})",
                flags=re.IGNORECASE,
            ),
        ),
        (
            "WRITES",
            re.compile(
                rf"\bTRUNCATE\s+TABLE\s+"
                rf"({_identifier_pattern()})",
                flags=re.IGNORECASE,
            ),
        ),
    )

    for relationship_type, pattern in write_patterns:
        references.extend(
            _matches_to_references(
                definition=definition,
                pattern=pattern,
                relationship_type=relationship_type,
            )
        )

        masked_definition = _mask_matches(
            definition=masked_definition,
            pattern=pattern,
        )

    read_patterns = (
        re.compile(
            rf"\bFROM\s+"
            rf"({_identifier_pattern()})",
            flags=re.IGNORECASE,
        ),
        re.compile(
            rf"\bJOIN\s+"
            rf"({_identifier_pattern()})",
            flags=re.IGNORECASE,
        ),
    )

    for pattern in read_patterns:
        references.extend(
            _matches_to_references(
                definition=masked_definition,
                pattern=pattern,
                relationship_type="READS",
            )
        )

    call_patterns = (
        re.compile(
            rf"\bCALL\s+"
            rf"({_identifier_pattern()})",
            flags=re.IGNORECASE,
        ),
        re.compile(
            rf"\bEXEC(?:UTE)?\s+"
            rf"({_identifier_pattern()})",
            flags=re.IGNORECASE,
        ),
    )

    for pattern in call_patterns:
        references.extend(
            _matches_to_references(
                definition=definition,
                pattern=pattern,
                relationship_type="CALLS",
            )
        )

    return references


def _matches_to_references(
    definition: str,
    pattern: re.Pattern[str],
    relationship_type: str,
) -> list[dict[str, str]]:
    references: list[dict[str, str]] = []

    for match in pattern.finditer(definition):
        token = _normalize_identifier(
            match.group(1)
        )

        if not token:
            continue

        references.append(
            {
                "token": token,
                "relationship_type": (
                    relationship_type
                ),
            }
        )

    return references


def _mask_matches(
    definition: str,
    pattern: re.Pattern[str],
) -> str:
    """
    Replace matched SQL fragments with spaces.

    Keeping the original string length preserves later regex positions
    and prevents write targets from being detected as read targets.
    """

    characters = list(definition)

    for match in pattern.finditer(definition):
        start, end = match.span()

        for index in range(start, end):
            characters[index] = " "

    return "".join(characters)


def _resolve_object(
    token: str,
    source_schema: str,
    catalog: dict[str, dict[str, Any]],
    short_name_index: dict[
        str,
        list[dict[str, Any]],
    ],
    relationship_type: str,
) -> tuple[dict[str, Any] | None, float]:
    """
    Resolve a parsed SQL identifier to one discovered object.

    Resolution order:
    1. Exact schema-qualified match
    2. Match in the source object's schema
    3. Unique database-wide short-name match
    """

    normalized_token = _normalize_identifier(
        token
    ).lower()

    if not normalized_token:
        return None, 0.0

    token_parts = normalized_token.split(".")

    if len(token_parts) >= 2:
        schema_name = token_parts[-2]
        object_name = token_parts[-1]

        qualified_token = _qualified_name(
            schema_name,
            object_name,
        ).lower()

        target = catalog.get(
            qualified_token
        )

        if target is not None:
            if _target_type_allowed(
                target=target,
                relationship_type=relationship_type,
            ):
                return target, 0.9

            return None, 0.0

    short_name = token_parts[-1]

    same_schema_name = _qualified_name(
        source_schema,
        short_name,
    ).lower()

    same_schema_target = catalog.get(
        same_schema_name
    )

    if same_schema_target is not None:
        if _target_type_allowed(
            target=same_schema_target,
            relationship_type=relationship_type,
        ):
            return same_schema_target, 0.85

        return None, 0.0

    matches = short_name_index.get(
        short_name,
        [],
    )

    allowed_matches = [
        item
        for item in matches
        if _target_type_allowed(
            target=item,
            relationship_type=relationship_type,
        )
    ]

    if len(allowed_matches) == 1:
        return allowed_matches[0], 0.75

    return None, 0.0


def _target_type_allowed(
    target: dict[str, Any],
    relationship_type: str,
) -> bool:
    target_type = str(
        target.get("object_type") or ""
    ).upper()

    if relationship_type in {
        "READS",
        "WRITES",
    }:
        return target_type in {
            "TABLE",
            "VIEW",
            "MATERIALIZED_VIEW",
        }

    if relationship_type == "CALLS":
        return target_type in {
            "PROCEDURE",
            "FUNCTION",
        }

    return True


def _evidence_source(
    source_type: str,
) -> str:
    mapping = {
        "VIEW": "VIEW_DEFINITION",
        "MATERIALIZED_VIEW": "VIEW_DEFINITION",
        "PROCEDURE": "PROCEDURE_DEFINITION",
        "FUNCTION": "FUNCTION_DEFINITION",
        "TRIGGER": "TRIGGER_DEFINITION",
    }

    return mapping.get(
        source_type,
        "DDL",
    )


def _remove_sql_comments(
    definition: str,
) -> str:
    """
    Remove SQL comments while preserving quoted SQL content.

    This is intentionally conservative and does not attempt to fully
    parse vendor-specific SQL grammars.
    """

    without_block_comments = re.sub(
        r"/\*.*?\*/",
        " ",
        definition,
        flags=re.DOTALL,
    )

    return re.sub(
        r"--[^\r\n]*",
        " ",
        without_block_comments,
    )


def _identifier_pattern() -> str:
    """
    Return a pattern supporting common database identifier styles.

    Supported examples:
    public.patients
    "public"."patients"
    `clinical`.`patients`
    [dbo].[patients]
    database.schema.table
    """

    identifier_part = (
        r'(?:'
        r'"(?:[^"]|"")*"'
        r'|`(?:[^`]|``)*`'
        r'|\[(?:[^\]]|\]\])*\]'
        r'|[A-Za-z_][\w$#@]*'
        r')'
    )

    return (
        rf"{identifier_part}"
        rf"(?:\s*\.\s*{identifier_part}){{0,2}}"
    )


def _normalize_identifier(
    identifier: str,
) -> str:
    """Remove database-specific identifier quoting and whitespace."""

    value = str(identifier or "").strip()

    if not value:
        return ""

    parts = re.split(
        r"\s*\.\s*",
        value,
    )

    normalized_parts = [
        _unquote_identifier(part)
        for part in parts
        if part.strip()
    ]

    return ".".join(normalized_parts)


def _unquote_identifier(
    identifier: str,
) -> str:
    value = str(identifier).strip()

    if (
        len(value) >= 2
        and value[0] == '"'
        and value[-1] == '"'
    ):
        return value[1:-1].replace(
            '""',
            '"',
        )

    if (
        len(value) >= 2
        and value[0] == "`"
        and value[-1] == "`"
    ):
        return value[1:-1].replace(
            "``",
            "`",
        )

    if (
        len(value) >= 2
        and value[0] == "["
        and value[-1] == "]"
    ):
        return value[1:-1].replace(
            "]]",
            "]",
        )

    return value


def _qualified_name(
    schema_name: str,
    object_name: str,
) -> str:
    return f"{schema_name}.{object_name}"