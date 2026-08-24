from __future__ import annotations

import re
from typing import Any

from src.models.schemas import DependencyEdge


def extract_catalog_dependencies(
    objects: list[dict[str, Any]],
) -> list[DependencyEdge]:
    """Create deterministic dependency edges from foreign-key metadata."""
    edges: list[DependencyEdge] = []

    for database_object in objects:
        if database_object.get("object_type") != "TABLE":
            continue

        source_name = _qualified_name(
            database_object["schema_name"],
            database_object["object_name"],
        )

        for foreign_key in database_object.get("foreign_keys", []):
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
                    source_column=foreign_key.get("source_column"),
                    target_column=foreign_key.get("target_column"),
                    evidence_source="SOURCE_CATALOG",
                    confidence=1.0,
                )
            )

    return edges


def parse_definition_dependencies(
    objects: list[dict[str, Any]],
) -> list[DependencyEdge]:
    """Extract conservative view and routine dependencies from stored DDL text."""
    catalog = {
        _qualified_name(item["schema_name"], item["object_name"]): item
        for item in objects
    }
    short_name_index: dict[str, list[dict[str, Any]]] = {}
    for item in objects:
        short_name_index.setdefault(item["object_name"].lower(), []).append(item)

    edges: list[DependencyEdge] = []
    seen: set[tuple[str, str, str]] = set()

    for source in objects:
        source_type = source.get("object_type")
        if source_type not in {"VIEW", "MATERIALIZED_VIEW", "PROCEDURE", "FUNCTION"}:
            continue

        definition = source.get("object_ddl") or ""
        if not definition.strip():
            continue

        source_name = _qualified_name(source["schema_name"], source["object_name"])
        referenced_tokens = _extract_relation_tokens(definition)

        for token in referenced_tokens:
            target = _resolve_object(token, catalog, short_name_index)
            if target is None:
                continue

            target_name = _qualified_name(target["schema_name"], target["object_name"])
            if source_name == target_name:
                continue

            relationship_type, evidence_source = _relationship_for(source_type)
            key = (source_name, target_name, relationship_type)
            if key in seen:
                continue
            seen.add(key)

            edges.append(
                DependencyEdge(
                    source_object=source_name,
                    source_object_type=source_type,
                    target_object=target_name,
                    target_object_type=target["object_type"],
                    relationship_type=relationship_type,
                    source_column=None,
                    target_column=None,
                    evidence_source=evidence_source,
                    confidence=0.9,
                )
            )

    return edges


def _qualified_name(schema_name: str, object_name: str) -> str:
    return f"{schema_name}.{object_name}"


def _extract_relation_tokens(definition: str) -> set[str]:
    pattern = re.compile(
        r"\b(?:FROM|JOIN|UPDATE|INTO)\s+([A-Za-z_][\w$]*(?:\.[A-Za-z_][\w$]*)?)",
        flags=re.IGNORECASE,
    )
    return {match.group(1).lower() for match in pattern.finditer(definition)}


def _resolve_object(token: str, catalog, short_name_index):
    if "." in token:
        return catalog.get(token.lower())

    matches = short_name_index.get(token.lower(), [])
    if len(matches) == 1:
        return matches[0]
    return None


def _relationship_for(source_type: str) -> tuple[str, str]:
    if source_type in {"VIEW", "MATERIALIZED_VIEW"}:
        return "VIEW_READS_TABLE", "VIEW_DEFINITION"
    if source_type == "PROCEDURE":
        return "PROCEDURE_READS_TABLE", "PROCEDURE_DEFINITION"
    return "FUNCTION_READS_TABLE", "FUNCTION_DEFINITION"
