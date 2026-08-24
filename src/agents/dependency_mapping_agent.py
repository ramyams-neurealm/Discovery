from __future__ import annotations

from src.agents.base import BaseAgent
from src.tools.dependency_tools import (
    extract_catalog_dependencies,
    parse_definition_dependencies,
)


class DependencyMappingAgent(BaseAgent):
    def run(self, objects):
        """Return deterministic catalog edges plus conservative DDL-derived edges."""
        exact_edges = extract_catalog_dependencies(objects)
        definition_edges = parse_definition_dependencies(objects)
        return exact_edges + definition_edges
