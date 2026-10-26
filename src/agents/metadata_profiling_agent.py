from __future__ import annotations

import logging
from typing import Any

from src.agents.base import BaseAgent
from src.repositories.discovery_repository import DiscoveryRepository
from src.tools.metadata_tools import discover_database_metadata
from src.tools.profiling_tools import (
    is_table_object,
    profile_tables,
)


logger = logging.getLogger(__name__)


class MetadataDiscoveryProfilingAgent(BaseAgent):
    def __init__(
        self,
        settings,
        key_vault,
        repository: DiscoveryRepository,
    ):
        super().__init__(settings, key_vault)
        self.repository = repository

    def run(
        self,
        run_id: str,
        connection_id: int,
        source_connection,
        selected_objects: list[dict[str, str]] | None = None,
    ) -> dict[str, Any]:
        source_connector = source_connection

        discovered_objects: list[dict[str, Any]] = []
        filtered_objects: list[dict[str, Any]] = []
        saved_objects: list[dict[str, Any]] = []

        table_profiles: list[dict[str, Any]] = []
        column_profiles: list[dict[str, Any]] = []

        profile_errors: list[str] = []

        normalized_selected_objects = (
            self._normalize_selected_objects(
                selected_objects or []
            )
        )

        logger.info(
            "Starting metadata profiling",
            extra={
                "discovery_run_id": run_id,
                "selected_object_count": len(
                    normalized_selected_objects
                ),
                "selected_objects": (
                    normalized_selected_objects
                ),
            },
        )

        try:
            self._configure_query_timeout(
                source_connector=source_connector,
                run_id=run_id,
            )

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
                message=(
                    "Discovering and profiling "
                    "selected database objects"
                ),
                processed_items=0,
                total_items=len(
                    normalized_selected_objects
                ),
                error_code=None,
                error_message=None,
            )

            logger.info(
                "Querying source database metadata",
                extra={
                    "discovery_run_id": run_id,
                    "selected_object_count": len(
                        normalized_selected_objects
                    ),
                },
            )

            discovered_objects = discover_database_metadata(
                source_connector=source_connector,
                selected_objects=(
                    normalized_selected_objects
                ),
            )

            if not isinstance(discovered_objects, list):
                raise TypeError(
                    "Metadata discovery did not return "
                    "a list of objects."
                )

            filtered_objects = self._filter_discovered_objects(
                discovered_objects=discovered_objects,
                selected_objects=(
                    normalized_selected_objects
                ),
            )

            if (
                normalized_selected_objects
                and not filtered_objects
            ):
                requested_names = ", ".join(
                    item["object_name"]
                    for item in normalized_selected_objects
                )

                raise ValueError(
                    "None of the selected objects were found "
                    "in the metadata discovery response. "
                    f"Requested objects: {requested_names}."
                )

            logger.info(
                "Source metadata filtering completed",
                extra={
                    "discovery_run_id": run_id,
                    "raw_discovered_object_count": len(
                        discovered_objects
                    ),
                    "filtered_object_count": len(
                        filtered_objects
                    ),
                    "selected_object_count": len(
                        normalized_selected_objects
                    ),
                },
            )

            saved_objects = (
                self.repository.save_discovered_metadata(
                    run_id=run_id,
                    connection_id=connection_id,
                    objects=filtered_objects,
                )
            )

            if not isinstance(saved_objects, list):
                saved_objects = []

            if (
                filtered_objects
                and not saved_objects
            ):
                raise RuntimeError(
                    "Selected metadata was discovered but "
                    "could not be saved."
                )

            objects_to_profile = saved_objects

            discovered_column_count = sum(
                len(item.get("columns") or [])
                for item in objects_to_profile
            )

            logger.info(
                "Sampling selected tables and columns",
                extra={
                    "discovery_run_id": run_id,
                    "object_count": len(
                        objects_to_profile
                    ),
                    "column_count": (
                        discovered_column_count
                    ),
                },
            )

            (
                table_profiles,
                column_profiles,
            ) = profile_tables(
                source_connector=source_connector,
                objects=objects_to_profile,
                errors=profile_errors,
            )

            table_profiles = table_profiles or []
            column_profiles = column_profiles or []

            empty_table_profiles = [
                profile
                for profile in table_profiles
                if profile.get("row_count") == 0
            ]

            table_objects = [
                item
                for item in objects_to_profile
                if is_table_object(item)
            ]

            missing_table_profiles = (
                bool(table_objects)
                and not table_profiles
            )

            saved_table_profiles = []
            saved_column_profiles = []

            if table_profiles or column_profiles:
                (
                    saved_table_profiles,
                    saved_column_profiles,
                ) = self.repository.save_profiles(
                    run_id=run_id,
                    table_profiles=table_profiles,
                    column_profiles=column_profiles,
                )

            saved_table_profiles = (
                saved_table_profiles or []
            )
            saved_column_profiles = (
                saved_column_profiles or []
            )

            total_objects = len(objects_to_profile)

            total_columns = (
                len(saved_column_profiles)
                if saved_column_profiles
                else discovered_column_count
            )

            empty_table_count = len(
                empty_table_profiles
            )

            warning_messages: list[str] = []

            if profile_errors:
                warning_messages.append(
                    (
                        "Metadata profiling completed with "
                        f"{len(profile_errors)} sampling "
                        "error(s)"
                    )
                )

            if missing_table_profiles:
                warning_messages.append(
                    (
                        "Metadata discovery returned tables "
                        "but no table profiles"
                    )
                )

            if not objects_to_profile:
                warning_messages.append(
                    "Metadata discovery returned no objects"
                )

            if warning_messages:
                stage_status = (
                    "COMPLETED_WITH_WARNINGS"
                )

                stage_message = (
                    "; ".join(warning_messages)
                    + (
                        f"; discovered {total_objects} "
                        f"object(s) and {total_columns} "
                        "column(s)"
                    )
                )
            else:
                stage_status = "COMPLETED"

                stage_message = (
                    f"Discovered {total_objects} object(s) "
                    f"and {total_columns} column(s)"
                )

                if empty_table_count:
                    stage_message += (
                        f"; {empty_table_count} table(s) "
                        "had zero rows"
                    )

            self.repository.update_stage(
                run_id=run_id,
                stage_name="METADATA_PROFILING",
                stage_status=stage_status,
                message=stage_message,
                processed_items=total_objects,
                total_items=total_objects,
                error_code=(
                    "METADATA_PROFILING_PARTIAL_FAILURE"
                    if profile_errors
                    else None
                ),
                error_message=(
                    "; ".join(profile_errors[:10])
                    if profile_errors
                    else None
                ),
            )

            self.repository.update_run_status(
                run_id=run_id,
                status="RUNNING",
                current_stage="METADATA_PROFILING",
                progress_percentage=35,
                error_code=None,
                error_message=None,
            )

            logger.info(
                "Metadata profiling completed",
                extra={
                    "discovery_run_id": run_id,
                    "profiled_object_count": (
                        total_objects
                    ),
                    "profiled_table_count": len(
                        saved_table_profiles
                    ),
                    "profiled_column_count": len(
                        saved_column_profiles
                    ),
                    "profile_error_count": len(
                        profile_errors
                    ),
                },
            )

            return {
                "profile_data": {
                    "selected_object_count": len(
                        normalized_selected_objects
                    ),
                    "discovered_object_count": (
                        total_objects
                    ),
                    "profiled_table_count": len(
                        saved_table_profiles
                    ),
                    "profiled_column_count": len(
                        saved_column_profiles
                    ),
                },
                "objects": objects_to_profile,
                "table_profiles": (
                    saved_table_profiles
                ),
                "column_profiles": (
                    saved_column_profiles
                ),
                "profile_errors": profile_errors,
                "metadata_error": None,
            }

        except Exception as error:
            safe_error = str(error)

            logger.error(
                (
                    "Metadata discovery or profiling "
                    "failed: %s"
                ),
                safe_error,
                exc_info=True,
                extra={
                    "discovery_run_id": run_id,
                },
            )

            self._record_profiling_failure(
                run_id=run_id,
                message="Metadata profiling failed",
                error_message=safe_error,
            )

            return {
                "profile_data": {},
                "objects": [],
                "table_profiles": [],
                "column_profiles": [],
                "profile_errors": profile_errors,
                "metadata_error": safe_error,
            }

    @staticmethod
    def _normalize_selected_objects(
        selected_objects: list[dict[str, str]],
    ) -> list[dict[str, str]]:
        normalized: list[dict[str, str]] = []
        seen: set[tuple[str, str, str]] = set()

        for selected_object in selected_objects:
            if not isinstance(selected_object, dict):
                raise ValueError(
                    "Every selected object must be "
                    "a JSON object."
                )

            object_name = str(
                selected_object.get("object_name")
                or selected_object.get("name")
                or ""
            ).strip()

            object_type = str(
                selected_object.get("object_type")
                or selected_object.get("type")
                or ""
            ).strip().upper()

            schema_name = str(
                selected_object.get("schema_name")
                or ""
            ).strip()

            if not object_name:
                raise ValueError(
                    "A selected object is missing "
                    "object_name."
                )

            if not object_type:
                raise ValueError(
                    (
                        f"Selected object '{object_name}' "
                        "is missing object_type."
                    )
                )

            object_key = (
                schema_name.casefold(),
                object_name.casefold(),
                object_type.casefold(),
            )

            if object_key in seen:
                continue

            seen.add(object_key)

            normalized_object = {
                "object_name": object_name,
                "object_type": object_type,
            }

            if schema_name:
                normalized_object["schema_name"] = (
                    schema_name
                )

            normalized.append(normalized_object)

        return normalized

    @classmethod
    def _filter_discovered_objects(
        cls,
        discovered_objects: list[dict[str, Any]],
        selected_objects: list[dict[str, str]],
    ) -> list[dict[str, Any]]:
        if not selected_objects:
            return discovered_objects

        selected_keys = {
            cls._object_key(selected_object)
            for selected_object in selected_objects
        }

        selected_name_type_keys = {
            (
                selected_object["object_name"]
                .strip()
                .casefold(),
                selected_object["object_type"]
                .strip()
                .casefold(),
            )
            for selected_object in selected_objects
        }

        filtered_objects: list[dict[str, Any]] = []

        for discovered_object in discovered_objects:
            if not isinstance(
                discovered_object,
                dict,
            ):
                continue

            discovered_key = cls._object_key(
                discovered_object
            )

            discovered_name_type_key = (
                str(
                    discovered_object.get(
                        "object_name"
                    )
                    or discovered_object.get("name")
                    or ""
                )
                .strip()
                .casefold(),
                str(
                    discovered_object.get(
                        "object_type"
                    )
                    or discovered_object.get("type")
                    or ""
                )
                .strip()
                .casefold(),
            )

            if (
                discovered_key in selected_keys
                or discovered_name_type_key
                in selected_name_type_keys
            ):
                filtered_objects.append(
                    discovered_object
                )

        return filtered_objects

    @staticmethod
    def _object_key(
        database_object: dict[str, Any],
    ) -> tuple[str, str, str]:
        schema_name = str(
            database_object.get("schema_name")
            or database_object.get("schema")
            or ""
        ).strip().casefold()

        object_name = str(
            database_object.get("object_name")
            or database_object.get("name")
            or database_object.get("table_name")
            or ""
        ).strip().casefold()

        object_type = str(
            database_object.get("object_type")
            or database_object.get("type")
            or ""
        ).strip().casefold()

        return (
            schema_name,
            object_name,
            object_type,
        )

    @staticmethod
    def _configure_query_timeout(
        source_connector,
        run_id: str,
    ) -> None:
        """
        Set a 30-second source query timeout where the
        database driver supports it.
        """

        connection = getattr(
            source_connector,
            "connection",
            None,
        )

        connector_name = (
            source_connector.__class__.__name__
        )

        try:
            if connection is None:
                raise RuntimeError(
                    (
                        "Source database connection "
                        "is unavailable"
                    )
                )

            if connector_name == "PostgreSQLConnector":
                connection.execute(
                    "SET statement_timeout = 30000"
                )

            elif connector_name == "MySQLConnector":
                cursor = connection.cursor()

                try:
                    cursor.execute(
                        (
                            "SET SESSION "
                            "max_execution_time = 30000"
                        )
                    )
                finally:
                    cursor.close()

            elif connector_name == "SQLServerConnector":
                connection.timeout = 30

            elif connector_name == "OracleConnector":
                connection.call_timeout = 30000

            else:
                raise RuntimeError(
                    (
                        "No query timeout is configured "
                        f"for {connector_name}"
                    )
                )

        except Exception as error:
            logger.error(
                (
                    "Could not configure source query "
                    "timeout for %s"
                ),
                connector_name,
                exc_info=True,
                extra={
                    "discovery_run_id": run_id,
                },
            )

            raise RuntimeError(
                (
                    "Could not configure source query "
                    f"timeout for {connector_name}"
                )
            ) from error

    def _record_profiling_failure(
        self,
        run_id: str,
        message: str,
        error_message: str,
    ) -> None:
        try:
            self.repository.update_stage(
                run_id=run_id,
                stage_name="METADATA_PROFILING",
                stage_status="FAILED",
                message=message,
                processed_items=0,
                total_items=0,
                error_code=(
                    "METADATA_DISCOVERY_FAILED"
                ),
                error_message=error_message,
            )

        except Exception:
            logger.error(
                (
                    "Could not update metadata "
                    "profiling failure status"
                ),
                exc_info=True,
                extra={
                    "discovery_run_id": run_id,
                },
            )

        try:
            self.repository.update_run_status(
                run_id=run_id,
                status="FAILED",
                current_stage="METADATA_PROFILING",
                progress_percentage=10,
                error_code=(
                    "METADATA_DISCOVERY_FAILED"
                ),
                error_message=error_message,
            )

        except Exception:
            logger.error(
                (
                    "Could not update Discovery run "
                    "after metadata failure"
                ),
                exc_info=True,
                extra={
                    "discovery_run_id": run_id,
                },
            )