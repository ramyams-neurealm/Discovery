from __future__ import annotations

from typing import Any


def discover_database_metadata(
    source_connector: Any,
    selected_objects: list[dict[str, str]] | None = None,
) -> list[dict[str, Any]]:
    """Discover metadata through the selected vendor connector."""
    if not selected_objects:
        return source_connector.discover_metadata()

    return source_connector.discover_metadata(
        selected_objects=selected_objects,
    )


def persist_discovered_metadata(
    run_id: str,
    objects: list[dict[str, Any]],
) -> None:
    """Deprecated placeholder retained for backward compatibility."""
    del run_id
    del objects
    raise NotImplementedError(
        "Use DiscoveryRepository.save_discovered_metadata instead."
    )
