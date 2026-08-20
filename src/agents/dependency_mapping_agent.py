from src.agents.base import BaseAgent
from src.tools.dependency_tools import extract_catalog_dependencies, parse_definition_dependencies


class DependencyMappingAgent(BaseAgent):
    def run(self, objects: list[dict]) -> list:
        exact_edges = extract_catalog_dependencies(objects)
        unresolved = parse_definition_dependencies(objects)
        # Add GPT-assisted resolution for unresolved references using the approved object catalog.
        # Exact catalog FK edges remain deterministic and should not be altered by the LLM.
        return exact_edges
