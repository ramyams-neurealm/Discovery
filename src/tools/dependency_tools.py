from src.models.schemas import DependencyEdge


def extract_catalog_dependencies(objects: list[dict]) -> list[DependencyEdge]:
    """Deterministically extract foreign-key edges from discovered catalog metadata."""
    return []


def parse_definition_dependencies(objects: list[dict]) -> list[dict]:
    """Return unresolved view/procedure references for agent interpretation."""
    return []
