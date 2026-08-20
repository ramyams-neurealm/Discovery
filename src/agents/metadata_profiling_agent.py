from src.agents.base import BaseAgent
from src.tools.metadata_tools import discover_database_metadata, persist_discovered_metadata
from src.tools.profiling_tools import profile_tables


class MetadataDiscoveryProfilingAgent(BaseAgent):
    def run(self, run_id: str, source_connection) -> dict:
        objects = discover_database_metadata(source_connection)
        persist_discovered_metadata(run_id, objects)
        table_profiles, column_profiles = profile_tables(source_connection, objects)
        return {
            "objects": objects,
            "table_profiles": table_profiles,
            "column_profiles": column_profiles,
        }
