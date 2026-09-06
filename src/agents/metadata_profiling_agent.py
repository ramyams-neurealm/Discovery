from __future__ import annotations

from src.agents.base import BaseAgent
from src.repositories.discovery_repository import DiscoveryRepository
from src.tools.metadata_tools import discover_database_metadata
from src.tools.profiling_tools import profile_tables


class MetadataDiscoveryProfilingAgent(BaseAgent):
    def __init__(self, settings, key_vault, repository: DiscoveryRepository):
        super().__init__(settings, key_vault)
        self.repository = repository

    def run(
        self,
        run_id: str,
        connection_id: int,
        source_connection,
        selected_objects: list[dict[str, str]] | None = None,
    ) -> dict:
        source_connector = source_connection
        self.repository.update_run_status(
            run_id=run_id,
            status="RUNNING",
            current_stage="METADATA_PROFILING",
            progress_percentage=10,
        )
        self.repository.update_stage(
            run_id=run_id,
            stage_name="METADATA_PROFILING",
            stage_status="RUNNING",
            message="Discovering and profiling database objects",
        )

        try:
            discovered_objects = discover_database_metadata(
                source_connector=source_connector,
                selected_objects=selected_objects,
            )
            saved_objects = self.repository.save_discovered_metadata(
                run_id=run_id,
                connection_id=connection_id,
                objects=discovered_objects,
            )
            table_profiles, column_profiles = profile_tables(
                source_connector=source_connector,
                objects=saved_objects,
            )
            saved_table_profiles, saved_column_profiles = self.repository.save_profiles(
                run_id=run_id,
                table_profiles=table_profiles,
                column_profiles=column_profiles,
            )

            total_objects = len(saved_objects)
            total_columns = sum(len(item.get("columns", [])) for item in saved_objects)
            self.repository.update_stage(
                run_id=run_id,
                stage_name="METADATA_PROFILING",
                stage_status="COMPLETED",
                message=f"Discovered {total_objects} objects and {total_columns} columns",
                processed_items=total_objects,
                total_items=total_objects,
            )
            self.repository.update_run_status(
                run_id=run_id,
                status="RUNNING",
                current_stage="METADATA_PROFILING",
                progress_percentage=35,
            )
            return {
                "objects": saved_objects,
                "table_profiles": saved_table_profiles,
                "column_profiles": saved_column_profiles,
            }

        except Exception as error:
            safe_error = f"Metadata discovery failed: {error.__class__.__name__}"
            self.repository.update_stage(
                run_id=run_id,
                stage_name="METADATA_PROFILING",
                stage_status="FAILED",
                message="Metadata discovery and profiling failed",
                error_code="METADATA_DISCOVERY_FAILED",
                error_message=safe_error,
            )
            self.repository.update_run_status(
                run_id=run_id,
                status="FAILED",
                current_stage="METADATA_PROFILING",
                progress_percentage=10,
                error_code="METADATA_DISCOVERY_FAILED",
                error_message=safe_error,
            )
            raise
