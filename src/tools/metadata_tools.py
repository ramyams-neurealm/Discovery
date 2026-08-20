from typing import Any


def discover_database_metadata(source_connection: Any) -> list[dict]:
    """Read-only vendor-specific catalog introspection tool."""
    raise NotImplementedError


def persist_discovered_metadata(run_id: str, objects: list[dict]) -> None:
    raise NotImplementedError
