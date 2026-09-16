from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any
from uuid import UUID

from sqlalchemy import text

from src.services.database import MetadataDatabase
from src.tools.hipaa_control_policy import evaluate_hipaa_controls


DISCOVERY_STAGES = [
    "CONNECTION_VALIDATION",
    "METADATA_PROFILING",
    "COLUMN_CLASSIFICATION",
    "DEPENDENCY_MAPPING",
    "REGULATORY_COMPLIANCE",
    "HIPAA_COMPLIANCE",
    "REPORT_FINALIZATION",
]


class DiscoveryRepository:
    def __init__(self, database: MetadataDatabase):
        self.database = database

    def list_compliance_frameworks(
        self,
        include_inactive: bool = False,
    ) -> list[dict[str, Any]]:
        query = text("""
            SELECT framework.framework_code, framework.framework_name,
                   framework.description, framework.region,
                   framework.implementation_status, framework.is_active,
                   policy.version, policy.status AS policy_status,
                   policy.scoring_enabled, policy.effective_from,
                   policy.effective_to
            FROM demooc28.compliance_frameworks AS framework
            LEFT JOIN LATERAL (
                SELECT version, status, scoring_enabled, effective_from,
                       effective_to, policy_pack_version_id
                FROM demooc28.policy_pack_versions
                WHERE framework_id = framework.framework_id
                ORDER BY CASE status WHEN 'ACTIVE' THEN 0 WHEN 'DRAFT' THEN 1 ELSE 2 END,
                         policy_pack_version_id DESC
                LIMIT 1
            ) AS policy ON TRUE
            WHERE (:include_inactive OR framework.is_active = TRUE)
            ORDER BY framework.framework_name
        """)
        with self.database.connect() as connection:
            rows = connection.execute(query, {"include_inactive": include_inactive}).mappings().all()
        result = []
        for row in rows:
            item = dict(row)
            version = item.pop("version", None)
            policy_status = item.pop("policy_status", None)
            scoring_enabled = item.pop("scoring_enabled", None)
            effective_from = item.pop("effective_from", None)
            effective_to = item.pop("effective_to", None)
            item["policy_pack"] = None if version is None else {
                "version": version, "status": policy_status,
                "scoring_enabled": scoring_enabled,
                "effective_from": effective_from, "effective_to": effective_to,
            }
            result.append(item)
        return result

    def validate_selected_frameworks(
        self,
        framework_codes: list[str],
    ) -> dict[str, list[str]]:
        """Separate selectable framework codes from invalid ones."""
        requested = list(dict.fromkeys(
            str(code).strip().upper()
            for code in framework_codes
            if str(code).strip()
        ))
        if not requested:
            return {
                "available": [],
                "unknown": [],
                "unavailable": [],
            }

        query = text("""
            SELECT
                framework.framework_code,
                framework.is_active,
                framework.implementation_status,
                EXISTS (
                    SELECT 1
                    FROM demooc28.policy_pack_versions AS policy
                    WHERE policy.framework_id = framework.framework_id
                      AND policy.status = 'ACTIVE'
                ) AS has_active_policy
            FROM demooc28.compliance_frameworks AS framework
            WHERE framework.framework_code = ANY(:framework_codes)
        """)
        with self.database.connect() as connection:
            rows = connection.execute(
                query,
                {"framework_codes": requested},
            ).mappings().all()

        found = {row["framework_code"]: row for row in rows}
        unknown = [code for code in requested if code not in found]
        available: list[str] = []
        unavailable: list[str] = []
        for code in requested:
            row = found.get(code)
            if row is None:
                continue
            if (
                row["is_active"]
                and row["implementation_status"] == "AVAILABLE"
                and row["has_active_policy"]
            ):
                available.append(code)
            else:
                unavailable.append(code)
        return {
            "available": available,
            "unknown": unknown,
            "unavailable": unavailable,
        }

    def create_run(
        self,
        run_id: UUID,
        connection_id: int,
        requested_scopes: list[str],
        effective_scopes: list[str] | None = None,
        selected_objects: list[dict[str, str]] | None = None,
        selected_frameworks: list[str] | None = None,
    ) -> None:
        effective_scopes = effective_scopes or requested_scopes
        selected_objects = selected_objects or []
        selected_frameworks = selected_frameworks or []

        query = text("""
            INSERT INTO demooc28.discovery_runs (
                discovery_run_id,
                connection_id,
                requested_scopes,
                effective_scopes,
                selected_objects,
                selected_frameworks,
                status,
                progress_percentage
            )
            VALUES (
                :run_id,
                :connection_id,
                CAST(:requested_scopes AS jsonb),
                CAST(:effective_scopes AS jsonb),
                CAST(:selected_objects AS jsonb),
                CAST(:selected_frameworks AS jsonb),
                'PENDING',
                0
            )
        """)

        with self.database.connect() as connection:
            connection.execute(
                query,
                {
                    "run_id": str(run_id),
                    "connection_id": connection_id,
                    "requested_scopes": json.dumps(
                        requested_scopes
                    ),
                    "effective_scopes": json.dumps(
                        effective_scopes
                    ),
                    "selected_objects": json.dumps(
                        selected_objects
                    ),
                    "selected_frameworks": json.dumps(
                        selected_frameworks
                    ),
                },
            )

    def create_run_stages(
        self,
        run_id: UUID,
        effective_scopes: list[str],
    ) -> None:
        """Create all workflow stages and timestamp skipped stages."""
        effective_scope_set = set(effective_scopes)
        stage_scope_mapping = {
            "COLUMN_CLASSIFICATION": "COLUMN_CLASSIFICATION",
            "DEPENDENCY_MAPPING": "DEPENDENCY_MAP",
            "REGULATORY_COMPLIANCE": "REGULATORY_COMPLIANCE",
            "HIPAA_COMPLIANCE": "HIPAA_COMPLIANCE",
        }
        query = text("""
            INSERT INTO demooc28.discovery_run_stages (
                discovery_run_id,
                stage_name,
                stage_status,
                message,
                completed_at
            ) VALUES (
                CAST(:run_id AS UUID),
                CAST(:stage_name AS VARCHAR(64)),
                CAST(:stage_status AS VARCHAR(32)),
                CAST(:message AS TEXT),
                CASE
                    WHEN CAST(:is_skipped AS BOOLEAN)
                    THEN CURRENT_TIMESTAMP
                    ELSE NULL
                END
            )
            ON CONFLICT (discovery_run_id, stage_name) DO NOTHING
        """)
        with self.database.connect() as connection:
            for stage_name in DISCOVERY_STAGES:
                required_scope = stage_scope_mapping.get(stage_name)
                is_skipped = bool(
                    required_scope
                    and required_scope not in effective_scope_set
                )
                stage_status = "SKIPPED" if is_skipped else "PENDING"
                message = "Stage not requested" if is_skipped else "Waiting to start"
                connection.execute(
                    query,
                    {
                        "run_id": str(run_id),
                        "stage_name": stage_name,
                        "stage_status": stage_status,
                        "message": message,
                        "is_skipped": is_skipped,
                    },
                )

    def get_run(self, run_id: UUID | str) -> dict[str, Any] | None:
        query = text("""
            SELECT * FROM demooc28.discovery_runs
            WHERE discovery_run_id = :run_id
        """)
        with self.database.connect() as connection:
            row = connection.execute(query, {"run_id": str(run_id)}).mappings().one_or_none()
        return dict(row) if row else None

    def get_datasource_connection(
        self,
        connection_id: int,
    ) -> dict[str, Any] | None:
        """Return safe datasource metadata without credential fields."""
        query = text(
            """
            SELECT
                connection_id,
                connection_name,
                database_type,
                host,
                port,
                database_name,
                schema_name,
                username,
                ssl_enabled,
                is_active,
                discovery_status,
                last_discovered_at,
                created_at,
                updated_at
            FROM demooc28.datasource_connections
            WHERE connection_id = :connection_id
            """
        )
        with self.database.connect() as connection:
            row = connection.execute(
                query,
                {"connection_id": connection_id},
            ).mappings().one_or_none()
        return dict(row) if row else None

    def get_datasource_for_run(
        self,
        run_id: UUID | str,
    ) -> dict[str, Any] | None:
        """Return safe datasource metadata required by the runner."""
        query = text("""
            SELECT
                datasource.connection_id,
                datasource.connection_name,
                datasource.database_type,
                datasource.host,
                datasource.port,
                datasource.database_name,
                datasource.schema_name,
                datasource.username,
                datasource.ssl_enabled,
                datasource.is_active,
                datasource.discovery_status
            FROM demooc28.discovery_runs AS discovery_run
            JOIN demooc28.datasource_connections AS datasource
              ON datasource.connection_id = discovery_run.connection_id
            WHERE discovery_run.discovery_run_id = CAST(:run_id AS UUID)
        """)
        with self.database.connect() as connection:
            row = connection.execute(
                query,
                {"run_id": str(run_id)},
            ).mappings().one_or_none()
        return dict(row) if row else None

    def update_run_status(
        self,
        run_id: UUID | str,
        status: str,
        current_stage: str | None = None,
        progress_percentage: float | None = None,
        error_code: str | None = None,
        error_message: str | None = None,
    ) -> None:
        query = text("""
            UPDATE demooc28.discovery_runs
            SET status = CAST(:status AS VARCHAR(32)),
                current_stage = CAST(:current_stage AS VARCHAR(64)),
                progress_percentage = COALESCE(
                    CAST(:progress_percentage AS NUMERIC(5,2)),
                    progress_percentage
                ),
                error_code = CAST(:error_code AS VARCHAR(64)),
                error_message = CAST(:error_message AS TEXT),
                completed_at = CASE
                    WHEN CAST(:status AS VARCHAR(32)) IN (
                        'SUCCEEDED',
                        'PARTIALLY_COMPLETED',
                        'FAILED',
                        'CANCELLED'
                    )
                    THEN CURRENT_TIMESTAMP
                    ELSE completed_at
                END
            WHERE discovery_run_id = CAST(:run_id AS UUID)
        """)
        with self.database.connect() as connection:
            connection.execute(query, {
                "run_id": str(run_id),
                "status": status,
                "current_stage": current_stage,
                "progress_percentage": progress_percentage,
                "error_code": error_code,
                "error_message": error_message,
            })

    def update_stage(
        self,
        run_id: UUID | str,
        stage_name: str,
        stage_status: str,
        message: str | None = None,
        processed_items: int = 0,
        total_items: int = 0,
        error_code: str | None = None,
        error_message: str | None = None,
    ) -> None:
        query = text("""
            UPDATE demooc28.discovery_run_stages
            SET stage_status = CAST(:stage_status AS VARCHAR(32)),
                message = CAST(:message AS TEXT),
                processed_items = CAST(:processed_items AS INTEGER),
                total_items = CAST(:total_items AS INTEGER),
                error_code = CAST(:error_code AS VARCHAR(64)),
                error_message = CAST(:error_message AS TEXT),
                started_at = CASE
                    WHEN CAST(:stage_status AS VARCHAR(32)) = 'RUNNING'
                         AND started_at IS NULL
                    THEN CURRENT_TIMESTAMP
                    ELSE started_at
                END,
                completed_at = CASE
                    WHEN CAST(:stage_status AS VARCHAR(32)) IN (
                        'COMPLETED',
                        'COMPLETED_WITH_WARNINGS',
                        'SKIPPED',
                        'FAILED',
                        'CANCELLED'
                    )
                    THEN CURRENT_TIMESTAMP
                    ELSE completed_at
                END
            WHERE discovery_run_id = CAST(:run_id AS UUID)
              AND stage_name = CAST(:stage_name AS VARCHAR(64))
        """)
        with self.database.connect() as connection:
            connection.execute(query, {
                "run_id": str(run_id),
                "stage_name": stage_name,
                "stage_status": stage_status,
                "message": message,
                "processed_items": processed_items,
                "total_items": total_items,
                "error_code": error_code,
                "error_message": error_message,
            })

    def save_discovered_object(
        self,
        run_id: UUID | str,
        connection_id: int,
        database_object: dict[str, Any],
    ) -> int:
        query = text("""
            INSERT INTO demooc28.discovered_objects (
                discovery_run_id, connection_id, schema_name, object_name,
                object_type, object_ddl, object_metadata
            ) VALUES (
                :run_id, :connection_id, :schema_name, :object_name,
                :object_type, :object_ddl, CAST(:object_metadata AS jsonb)
            )
            ON CONFLICT (discovery_run_id, schema_name, object_name, object_type)
            DO UPDATE SET object_ddl = EXCLUDED.object_ddl,
                          object_metadata = EXCLUDED.object_metadata
            RETURNING object_id
        """)
        with self.database.connect() as connection:
            object_id = connection.execute(query, {
                "run_id": str(run_id),
                "connection_id": connection_id,
                "schema_name": database_object["schema_name"],
                "object_name": database_object["object_name"],
                "object_type": database_object["object_type"],
                "object_ddl": database_object.get("object_ddl"),
                "object_metadata": json.dumps(database_object.get("object_metadata", {})),
            }).scalar_one()
        return int(object_id)

    def save_discovered_column(
        self,
        run_id: UUID | str,
        object_id: int,
        column: dict[str, Any],
    ) -> int:
        query = text("""
            INSERT INTO demooc28.discovered_columns (
                discovery_run_id, object_id, column_name, ordinal_position,
                data_type, nullable, default_value, is_primary_key,
                is_foreign_key, column_metadata
            ) VALUES (
                :run_id, :object_id, :column_name, :ordinal_position,
                :data_type, :nullable, :default_value, :is_primary_key,
                :is_foreign_key, CAST(:column_metadata AS jsonb)
            )
            ON CONFLICT (discovery_run_id, object_id, column_name)
            DO UPDATE SET ordinal_position = EXCLUDED.ordinal_position,
                          data_type = EXCLUDED.data_type,
                          nullable = EXCLUDED.nullable,
                          default_value = EXCLUDED.default_value,
                          is_primary_key = EXCLUDED.is_primary_key,
                          is_foreign_key = EXCLUDED.is_foreign_key,
                          column_metadata = EXCLUDED.column_metadata
            RETURNING column_id
        """)
        with self.database.connect() as connection:
            column_id = connection.execute(query, {
                "run_id": str(run_id),
                "object_id": object_id,
                "column_name": column["column_name"],
                "ordinal_position": column.get("ordinal_position"),
                "data_type": column["data_type"],
                "nullable": column.get("nullable"),
                "default_value": column.get("default_value"),
                "is_primary_key": column.get("is_primary_key", False),
                "is_foreign_key": column.get("is_foreign_key", False),
                "column_metadata": json.dumps(column.get("column_metadata", {})),
            }).scalar_one()
        return int(column_id)

    def save_discovered_metadata(
        self,
        run_id: UUID | str,
        connection_id: int,
        objects: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        saved_objects = []
        for database_object in objects:
            object_id = self.save_discovered_object(run_id, connection_id, database_object)
            saved_object = {**database_object, "object_id": object_id, "columns": []}
            for column in database_object.get("columns", []):
                column_id = self.save_discovered_column(run_id, object_id, column)
                saved_object["columns"].append({
                    **column,
                    "column_id": column_id,
                    "object_id": object_id,
                    "schema_name": database_object["schema_name"],
                    "table_name": database_object["object_name"],
                })
            saved_objects.append(saved_object)
        return saved_objects

    def save_table_profile(self, run_id: UUID | str, profile: dict[str, Any]) -> int:
        query = text("""
            INSERT INTO demooc28.table_profiles (
                discovery_run_id, object_id, row_count, column_count,
                average_null_percentage, profiling_method, profile_metadata
            ) VALUES (
                :run_id, :object_id, :row_count, :column_count,
                :average_null_percentage, :profiling_method,
                CAST(:profile_metadata AS jsonb)
            )
            ON CONFLICT (discovery_run_id, object_id)
            DO UPDATE SET row_count = EXCLUDED.row_count,
                          column_count = EXCLUDED.column_count,
                          average_null_percentage = EXCLUDED.average_null_percentage,
                          profiling_method = EXCLUDED.profiling_method,
                          profile_metadata = EXCLUDED.profile_metadata
            RETURNING table_profile_id
        """)
        with self.database.connect() as connection:
            profile_id = connection.execute(query, {
                "run_id": str(run_id),
                "object_id": profile["object_id"],
                "row_count": profile.get("row_count"),
                "column_count": profile["column_count"],
                "average_null_percentage": profile.get("average_null_percentage"),
                "profiling_method": profile.get("profiling_method", "EXACT"),
                "profile_metadata": json.dumps(profile.get("profile_metadata", {})),
            }).scalar_one()
        return int(profile_id)

    def save_column_profile(self, run_id: UUID | str, profile: dict[str, Any]) -> int:
        query = text("""
            INSERT INTO demooc28.column_profiles (
                discovery_run_id, column_id, null_percentage, distinct_count,
                distinct_count_is_approximate, masked_samples, profile_metadata
            ) VALUES (
                :run_id, :column_id, :null_percentage, :distinct_count,
                :distinct_count_is_approximate, CAST(:masked_samples AS jsonb),
                CAST(:profile_metadata AS jsonb)
            )
            ON CONFLICT (discovery_run_id, column_id)
            DO UPDATE SET null_percentage = EXCLUDED.null_percentage,
                          distinct_count = EXCLUDED.distinct_count,
                          distinct_count_is_approximate = EXCLUDED.distinct_count_is_approximate,
                          masked_samples = EXCLUDED.masked_samples,
                          profile_metadata = EXCLUDED.profile_metadata
            RETURNING column_profile_id
        """)
        with self.database.connect() as connection:
            profile_id = connection.execute(query, {
                "run_id": str(run_id),
                "column_id": profile["column_id"],
                "null_percentage": profile.get("null_percentage"),
                "distinct_count": profile.get("distinct_count"),
                "distinct_count_is_approximate": profile.get(
                    "distinct_count_is_approximate", False
                ),
                "masked_samples": json.dumps(profile.get("masked_samples", [])),
                "profile_metadata": json.dumps(profile.get("profile_metadata", {})),
            }).scalar_one()
        return int(profile_id)

    def save_profiles(
        self,
        run_id: UUID | str,
        table_profiles: list[dict[str, Any]],
        column_profiles: list[dict[str, Any]],
    ):
        saved_table_profiles = []
        saved_column_profiles = []

        for profile in table_profiles:
            profile_id = self.save_table_profile(run_id, profile)
            saved_table_profiles.append({
                **profile,
                "table_profile_id": profile_id,
                "discovery_run_id": str(run_id),
            })

        for profile in column_profiles:
            profile_id = self.save_column_profile(run_id, profile)
            saved_column_profiles.append({
                **profile,
                "column_profile_id": profile_id,
                "discovery_run_id": str(run_id),
            })

        return saved_table_profiles, saved_column_profiles

    def save_classification(
        self,
        run_id: UUID | str,
        column_id: int,
        result,
        classifier_version: str = "classification-agent-v1",
    ) -> int:
        """Insert or update one column-classification result."""
        payload = (
            result.model_dump()
            if hasattr(result, "model_dump")
            else dict(result)
        )

        query = text("""
            INSERT INTO demooc28.column_classifications (
                discovery_run_id,
                column_id,
                display_classification,
                sensitive_data_type,
                sensitivity_level,
                is_sensitive,
                confidence,
                reason,
                inference_basis,
                needs_human_review,
                review_reason,
                classifier_type,
                classifier_version,
                evidence_mode,
                verification_status
            )
            VALUES (
                :run_id,
                :column_id,
                :display_classification,
                :sensitive_data_type,
                :sensitivity_level,
                :is_sensitive,
                :confidence,
                :reason,
                CAST(:inference_basis AS jsonb),
                :needs_human_review,
                :review_reason,
                'GPT_4O',
                :classifier_version,
                'SAMPLED_PROFILE',
                'PROVISIONAL'
            )
            ON CONFLICT (discovery_run_id, column_id)
            DO UPDATE SET
                display_classification = EXCLUDED.display_classification,
                sensitive_data_type = EXCLUDED.sensitive_data_type,
                sensitivity_level = EXCLUDED.sensitivity_level,
                is_sensitive = EXCLUDED.is_sensitive,
                confidence = EXCLUDED.confidence,
                reason = EXCLUDED.reason,
                inference_basis = EXCLUDED.inference_basis,
                needs_human_review = EXCLUDED.needs_human_review,
                review_reason = EXCLUDED.review_reason,
                classifier_type = EXCLUDED.classifier_type,
                classifier_version = EXCLUDED.classifier_version,
                evidence_mode = EXCLUDED.evidence_mode,
                verification_status = EXCLUDED.verification_status
            RETURNING classification_id
        """)

        display_classification = payload["display_classification"]
        if hasattr(display_classification, "value"):
            display_classification = display_classification.value

        sensitivity_level = payload.get("sensitivity_level")
        allowed_sensitivity_levels = {
            "PUBLIC",
            "INTERNAL",
            "CONFIDENTIAL",
            "RESTRICTED",
        }
        if sensitivity_level not in allowed_sensitivity_levels:
            sensitivity_level = (
                "RESTRICTED"
                if payload.get("is_sensitive", False)
                else "PUBLIC"
            )

        with self.database.connect() as connection:
            classification_id = connection.execute(
                query,
                {
                    "run_id": str(run_id),
                    "column_id": column_id,
                    "display_classification": display_classification,
                    "sensitive_data_type": payload.get(
                        "sensitive_data_type"
                    ),
                    "sensitivity_level": sensitivity_level,
                    "is_sensitive": payload["is_sensitive"],
                    "confidence": payload["confidence"],
                    "reason": payload["reason"],
                    "inference_basis": json.dumps(
                        payload.get("inference_basis", [])
                    ),
                    "needs_human_review": payload.get(
                        "needs_human_review", False
                    ),
                    "review_reason": payload.get("review_reason"),
                    "classifier_version": classifier_version,
                },
            ).scalar_one()

        return int(classification_id)

    def save_classifications(
        self,
        run_id: UUID | str,
        results,
        column_ids_by_key: dict[tuple[str, str, str], int],
    ):
        """Persist classification results and attach classification IDs."""
        saved_results = []

        for result in results:
            payload = (
                result.model_dump()
                if hasattr(result, "model_dump")
                else dict(result)
            )
            key = (
                payload["schema_name"],
                payload["table_name"],
                payload["column_name"],
            )
            column_id = column_ids_by_key.get(key)
            if column_id is None:
                raise ValueError(
                    "No discovered column ID found for "
                    f"{key[0]}.{key[1]}.{key[2]}"
                )

            classification_id = self.save_classification(
                run_id=run_id,
                column_id=column_id,
                result=result,
            )
            saved_results.append(
                {
                    **payload,
                    "classification_id": classification_id,
                    "column_id": column_id,
                }
            )

        return saved_results

    def save_dependency_edge(
        self,
        run_id: UUID | str,
        edge,
        object_ids_by_name: dict[str, int],
    ) -> int:
        """Insert or update one dependency edge."""
        payload = edge.model_dump() if hasattr(edge, "model_dump") else dict(edge)
        source_object_id = object_ids_by_name.get(payload["source_object"])
        target_object_id = object_ids_by_name.get(payload["target_object"])

        if source_object_id is None:
            raise ValueError(
                f"Source object not found: {payload['source_object']}"
            )
        if target_object_id is None:
            raise ValueError(
                f"Target object not found: {payload['target_object']}"
            )

        query = text("""
            INSERT INTO demooc28.dependency_edges (
                discovery_run_id,
                source_object_id,
                target_object_id,
                relationship_type,
                source_column,
                target_column,
                evidence_source,
                confidence,
                verification_status,
                details
            )
            VALUES (
                :run_id,
                :source_object_id,
                :target_object_id,
                :relationship_type,
                :source_column,
                :target_column,
                :evidence_source,
                :confidence,
                'PROVISIONAL',
                CAST(:details AS jsonb)
            )
            ON CONFLICT (
                discovery_run_id,
                source_object_id,
                target_object_id,
                relationship_type,
                COALESCE(source_column, ''),
                COALESCE(target_column, '')
            )
            DO UPDATE SET
                evidence_source = EXCLUDED.evidence_source,
                confidence = EXCLUDED.confidence,
                details = EXCLUDED.details
            RETURNING edge_id
        """)

        details = {
            "source_object": payload["source_object"],
            "source_object_type": payload["source_object_type"],
            "target_object": payload["target_object"],
            "target_object_type": payload["target_object_type"],
        }

        with self.database.connect() as connection:
            edge_id = connection.execute(
                query,
                {
                    "run_id": str(run_id),
                    "source_object_id": source_object_id,
                    "target_object_id": target_object_id,
                    "relationship_type": payload["relationship_type"],
                    "source_column": payload.get("source_column"),
                    "target_column": payload.get("target_column"),
                    "evidence_source": payload["evidence_source"],
                    "confidence": payload.get("confidence"),
                    "details": json.dumps(details),
                },
            ).scalar_one()

        return int(edge_id)

    def save_dependencies(
        self,
        run_id: UUID | str,
        edges,
        objects: list[dict[str, Any]],
    ):
        """
        Persist dependency edges whose source and target objects
        are both included in the current discovery run.

        References outside a limited smoke-test object set are
        skipped instead of failing the entire discovery run.
        """

        object_ids_by_name = {
            (
                f"{item['schema_name']}."
                f"{item['object_name']}"
            ): item["object_id"]
            for item in objects
        }

        saved_edges = []

        for edge in edges:
            payload = (
                edge.model_dump()
                if hasattr(edge, "model_dump")
                else dict(edge)
            )

            source_name = payload["source_object"]
            target_name = payload["target_object"]

            if source_name not in object_ids_by_name:
                continue

            if target_name not in object_ids_by_name:
                continue

            edge_id = self.save_dependency_edge(
                run_id=run_id,
                edge=edge,
                object_ids_by_name=object_ids_by_name,
            )

            saved_edges.append(
                {
                    **payload,
                    "edge_id": edge_id,
                }
            )

        return saved_edges

    def save_hipaa_finding(
        self,
        run_id: UUID | str,
        classification_id: int,
        finding,
        agent_version: str = "hipaa-agent-v1",
    ) -> int:
        """Insert or update one HIPAA finding."""

        payload = (
            finding.model_dump()
            if hasattr(finding, "model_dump")
            else dict(finding)
        )

        severity = payload["severity"]

        if hasattr(severity, "value"):
            severity = severity.value

        if severity in {"NEEDS_REVIEW", "SERIOUS", "CRITICAL"}:
            payload["needs_human_review"] = True
            payload["review_reason"] = (
                payload.get("review_reason")
                or "Human review is required because applicable controls "
                   "could not be verified from the supplied metadata."
            )

        payload["verification_status"] = "PROVISIONAL"

        raw_verification_status = str(
            payload.get(
                "verification_status",
                "PROVISIONAL",
            )
        ).strip().upper()

        verification_status_mapping = {
            "PROVISIONAL": "PROVISIONAL",
            "UNVERIFIED": "PROVISIONAL",
            "CONTROL VERIFICATION NEEDED": "PROVISIONAL",
            "CONTROL VERIFICATION REQUIRED": "PROVISIONAL",
            "VERIFICATION NEEDED": "PROVISIONAL",
            "VERIFICATION REQUIRED": "PROVISIONAL",
            "PENDING": "PROVISIONAL",
            "NOT VERIFIED": "PROVISIONAL",
            "REVIEWED": "REVIEWED",
            "CONFIRMED": "CONFIRMED",
            "REJECTED": "REJECTED",
        }

        verification_status = verification_status_mapping.get(
            raw_verification_status,
            "PROVISIONAL",
        )

        query = text("""
            INSERT INTO demooc28.hipaa_findings (
                discovery_run_id,
                classification_id,
                severity,
                finding,
                recommendation,
                confidence,
                needs_human_review,
                review_reason,
                verification_status,
                agent_version
            )
            VALUES (
                :run_id,
                :classification_id,
                :severity,
                :finding,
                :recommendation,
                :confidence,
                :needs_human_review,
                :review_reason,
                :verification_status,
                :agent_version
            )
            ON CONFLICT (
                discovery_run_id,
                classification_id
            )
            DO UPDATE SET
                severity = EXCLUDED.severity,
                finding = EXCLUDED.finding,
                recommendation = EXCLUDED.recommendation,
                confidence = EXCLUDED.confidence,
                needs_human_review =
                    EXCLUDED.needs_human_review,
                review_reason = EXCLUDED.review_reason,
                verification_status =
                    EXCLUDED.verification_status,
                agent_version = EXCLUDED.agent_version
            RETURNING finding_id
        """)

        with self.database.connect() as connection:
            finding_id = connection.execute(
                query,
                {
                    "run_id": str(run_id),
                    "classification_id": classification_id,
                    "severity": severity,
                    "finding": payload["finding"],
                    "recommendation": payload["recommendation"],
                    "confidence": payload["confidence"],
                    "needs_human_review": payload.get(
                        "needs_human_review",
                        False,
                    ),
                    "review_reason": payload.get(
                        "review_reason"
                    ),
                    "verification_status": verification_status,
                    "agent_version": agent_version,
                },
            ).scalar_one()

        return int(finding_id)


    def save_hipaa_findings(
        self,
        run_id: UUID | str,
        findings,
        classification_records: list[dict[str, Any]],
    ):
        """Persist HIPAA findings by matching table and column names."""
        classification_ids_by_key = {
            (record["table_name"], record["column_name"]): record[
                "classification_id"
            ]
            for record in classification_records
        }
        saved_findings = []

        for finding in findings:
            payload = (
                finding.model_dump()
                if hasattr(finding, "model_dump")
                else dict(finding)
            )
            key = (payload["table_name"], payload["column_name"])
            classification_id = classification_ids_by_key.get(key)
            if classification_id is None:
                raise ValueError(
                    "No classification ID found for HIPAA finding: "
                    f"{key[0]}.{key[1]}"
                )

            finding_id = self.save_hipaa_finding(
                run_id=run_id,
                classification_id=classification_id,
                finding=finding,
            )
            saved_findings.append(
                {
                    **payload,
                    "finding_id": finding_id,
                    "classification_id": classification_id,
                }
            )

        return saved_findings

    def save_hipaa_score(self, run_id: UUID | str, score) -> int:
        """Insert or update the deterministic HIPAA score for one run."""
        payload = score.model_dump() if hasattr(score, "model_dump") else dict(score)

        query = text("""
            INSERT INTO demooc28.hipaa_scores (
                discovery_run_id,
                score,
                risk_band,
                phi_columns_checked,
                severity_counts,
                policy_version
            )
            VALUES (
                :run_id,
                :score,
                :risk_band,
                :phi_columns_checked,
                CAST(:severity_counts AS jsonb),
                :policy_version
            )
            ON CONFLICT (discovery_run_id)
            DO UPDATE SET
                score = EXCLUDED.score,
                risk_band = EXCLUDED.risk_band,
                phi_columns_checked = EXCLUDED.phi_columns_checked,
                severity_counts = EXCLUDED.severity_counts,
                policy_version = EXCLUDED.policy_version,
                calculated_at = CURRENT_TIMESTAMP
            RETURNING score_id
        """)

        with self.database.connect() as connection:
            score_id = connection.execute(
                query,
                {
                    "run_id": str(run_id),
                    "score": payload["score"],
                    "risk_band": payload["risk_band"],
                    "phi_columns_checked": payload[
                        "phi_columns_checked"
                    ],
                    "severity_counts": json.dumps(
                        payload["severity_counts"]
                    ),
                    "policy_version": payload["policy_version"],
                },
            ).scalar_one()

        return int(score_id)


    def save_control_assessment(
        self,
        run_id: UUID | str,
        framework_code: str,
        classification_records: list[dict[str, Any]],
        evaluator: Callable,
        finding_builder: Callable | None = None,
    ) -> dict[str, Any]:
        """Evaluate and persist one policy pack through the shared engine."""
        framework_code = framework_code.strip().upper()
        setup_query = text("""
            SELECT framework.framework_id,
                   policy.policy_pack_version_id,
                   policy.version AS catalog_policy_version
            FROM demooc28.compliance_frameworks AS framework
            JOIN demooc28.policy_pack_versions AS policy
              ON policy.framework_id = framework.framework_id
             AND policy.status = 'ACTIVE'
            WHERE framework.framework_code = :framework_code
              AND framework.is_active = TRUE
            ORDER BY policy.policy_pack_version_id DESC
            LIMIT 1
        """)
        controls_query = text("""
            SELECT control_code, control_title, evidence_type,
                   evaluation_type, default_severity, weight
            FROM demooc28.framework_controls
            WHERE policy_pack_version_id = :policy_pack_version_id
              AND is_active = TRUE
            ORDER BY control_code
        """)
        assessment_query = text("""
            INSERT INTO demooc28.compliance_assessments (
                discovery_run_id, framework_id, policy_pack_version_id,
                status, started_at, completed_at
            ) VALUES (
                CAST(:run_id AS UUID), :framework_id,
                :policy_pack_version_id, 'COMPLETED',
                CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
            )
            ON CONFLICT (
                discovery_run_id, framework_id, policy_pack_version_id
            ) DO UPDATE SET
                status = 'COMPLETED',
                completed_at = CURRENT_TIMESTAMP
            RETURNING assessment_id
        """)
        insert_control_query = text("""
            INSERT INTO demooc28.compliance_control_results (
                assessment_id, control_code, control_title,
                assessment_status, severity, explanation,
                confidence, needs_human_review
            ) VALUES (
                :assessment_id, :control_code, :control_title,
                :assessment_status, :severity, :explanation,
                :confidence, :needs_human_review
            )
        """)
        finding_query = text("""
            INSERT INTO demooc28.compliance_findings (
                assessment_id, classification_id, severity,
                assessment_status, finding, recommendation, confidence,
                needs_human_review, review_reason, verification_status,
                source_finding_type, source_finding_id
            ) VALUES (
                :assessment_id, :classification_id, :severity,
                :assessment_status, :finding, :recommendation, :confidence,
                :needs_human_review, :review_reason, :verification_status,
                :source_finding_type, :source_finding_id
            )
            ON CONFLICT (
                assessment_id, source_finding_type, source_finding_id
            ) WHERE source_finding_type IS NOT NULL
                    AND source_finding_id IS NOT NULL
            DO UPDATE SET
                classification_id = EXCLUDED.classification_id,
                severity = EXCLUDED.severity,
                assessment_status = EXCLUDED.assessment_status,
                finding = EXCLUDED.finding,
                recommendation = EXCLUDED.recommendation,
                confidence = EXCLUDED.confidence,
                needs_human_review = EXCLUDED.needs_human_review,
                review_reason = EXCLUDED.review_reason,
                verification_status = EXCLUDED.verification_status
            RETURNING compliance_finding_id
        """)
        score_query = text("""
            INSERT INTO demooc28.compliance_scores (
                assessment_id, score, risk_band, scoring_method,
                evidence_coverage, applicable_controls, assessed_controls,
                status_counts, score_metadata
            ) VALUES (
                :assessment_id, :score, :risk_band,
                'CONTROL_PACK_INITIAL_ASSESSMENT', :evidence_coverage,
                :applicable_controls, :assessed_controls,
                CAST(:status_counts AS jsonb), CAST(:score_metadata AS jsonb)
            )
            ON CONFLICT (assessment_id) DO UPDATE SET
                score = EXCLUDED.score,
                risk_band = EXCLUDED.risk_band,
                scoring_method = EXCLUDED.scoring_method,
                evidence_coverage = EXCLUDED.evidence_coverage,
                applicable_controls = EXCLUDED.applicable_controls,
                assessed_controls = EXCLUDED.assessed_controls,
                status_counts = EXCLUDED.status_counts,
                score_metadata = EXCLUDED.score_metadata,
                calculated_at = CURRENT_TIMESTAMP
            RETURNING compliance_score_id
        """)
        with self.database.connect() as connection:
            setup = connection.execute(
                setup_query, {"framework_code": framework_code}
            ).mappings().one_or_none()
            if setup is None:
                raise ValueError(
                    f"Active policy-pack version not found: {framework_code}"
                )
            controls = [
                dict(row)
                for row in connection.execute(
                    controls_query,
                    {
                        "policy_pack_version_id": setup[
                            "policy_pack_version_id"
                        ]
                    },
                ).mappings().all()
            ]
            if not controls:
                raise ValueError(
                    f"Policy pack contains no controls: {framework_code}"
                )
            control_results, summary = evaluator(
                controls, classification_records
            )
            assessment_id = int(connection.execute(
                assessment_query,
                {
                    "run_id": str(run_id),
                    "framework_id": setup["framework_id"],
                    "policy_pack_version_id": setup[
                        "policy_pack_version_id"
                    ],
                },
            ).scalar_one())
            connection.execute(
                text("""
                    DELETE FROM demooc28.compliance_control_results
                    WHERE assessment_id = :assessment_id
                """),
                {"assessment_id": assessment_id},
            )
            for control_result in control_results:
                connection.execute(
                    insert_control_query,
                    {
                        "assessment_id": assessment_id,
                        **control_result,
                    },
                )
            finding_ids: list[int] = []
            if finding_builder is not None:
                for finding in finding_builder(classification_records):
                    finding_id = int(connection.execute(
                        finding_query,
                        {"assessment_id": assessment_id, **finding},
                    ).scalar_one())
                    finding_ids.append(finding_id)

            score_metadata = {
                "framework_code": framework_code,
                "policy_version": summary["policy_version"],
                "provisional": True,
                "minimum_evidence_coverage": 50,
                "weights": "EQUAL",
                "score_label": "INTERNAL_ASSESSMENT_SCORE",
            }
            for key, value in summary.items():
                if key.endswith("_columns_checked"):
                    score_metadata[key] = value
            score_id = int(connection.execute(
                score_query,
                {
                    "assessment_id": assessment_id,
                    "score": summary["score"],
                    "risk_band": summary["risk_band"],
                    "evidence_coverage": summary["evidence_coverage"],
                    "applicable_controls": summary[
                        "applicable_controls"
                    ],
                    "assessed_controls": summary["assessed_controls"],
                    "status_counts": json.dumps(
                        summary["status_counts"]
                    ),
                    "score_metadata": json.dumps(score_metadata),
                },
            ).scalar_one())
        return {
            "assessment_id": assessment_id,
            "score_id": score_id,
            "finding_ids": finding_ids,
            "summary": summary,
        }

    def save_hipaa_control_assessment(
        self,
        run_id: UUID | str,
        classification_records: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Compatibility wrapper retained for existing callers."""
        return self.save_control_assessment(
            run_id=run_id,
            framework_code="HIPAA",
            classification_records=classification_records,
            evaluator=evaluate_hipaa_controls,
        )

    def save_generic_hipaa_result(
        self,
        run_id: UUID | str,
        hipaa_findings: list[dict[str, Any]],
        hipaa_score: Any,
    ) -> dict[str, Any]:
        """Dual-write legacy HIPAA output into generic compliance tables."""
        score_payload = (
            hipaa_score.model_dump()
            if hasattr(hipaa_score, "model_dump")
            else dict(hipaa_score)
        )
        framework_query = text("""
            SELECT
                framework.framework_id,
                policy.policy_pack_version_id
            FROM demooc28.compliance_frameworks AS framework
            JOIN demooc28.policy_pack_versions AS policy
              ON policy.framework_id = framework.framework_id
             AND policy.status = 'ACTIVE'
            WHERE framework.framework_code = 'HIPAA'
              AND framework.is_active = TRUE
              AND framework.implementation_status = 'AVAILABLE'
            ORDER BY policy.policy_pack_version_id DESC
            LIMIT 1
        """)
        assessment_query = text("""
            INSERT INTO demooc28.compliance_assessments (
                discovery_run_id,
                framework_id,
                policy_pack_version_id,
                status,
                started_at,
                completed_at
            ) VALUES (
                CAST(:run_id AS UUID),
                :framework_id,
                :policy_pack_version_id,
                'COMPLETED',
                CURRENT_TIMESTAMP,
                CURRENT_TIMESTAMP
            )
            ON CONFLICT (
                discovery_run_id,
                framework_id,
                policy_pack_version_id
            ) DO UPDATE SET
                status = 'COMPLETED',
                completed_at = CURRENT_TIMESTAMP
            RETURNING assessment_id
        """)
        finding_query = text("""
            INSERT INTO demooc28.compliance_findings (
                assessment_id,
                classification_id,
                severity,
                assessment_status,
                finding,
                recommendation,
                confidence,
                needs_human_review,
                review_reason,
                verification_status,
                source_finding_type,
                source_finding_id
            ) VALUES (
                :assessment_id,
                :classification_id,
                :severity,
                :assessment_status,
                :finding,
                :recommendation,
                :confidence,
                :needs_human_review,
                :review_reason,
                :verification_status,
                'HIPAA_FINDING',
                :source_finding_id
            )
            ON CONFLICT (
                assessment_id,
                source_finding_type,
                source_finding_id
            ) WHERE source_finding_type IS NOT NULL
                    AND source_finding_id IS NOT NULL
            DO UPDATE SET
                classification_id = EXCLUDED.classification_id,
                severity = EXCLUDED.severity,
                assessment_status = EXCLUDED.assessment_status,
                finding = EXCLUDED.finding,
                recommendation = EXCLUDED.recommendation,
                confidence = EXCLUDED.confidence,
                needs_human_review = EXCLUDED.needs_human_review,
                review_reason = EXCLUDED.review_reason,
                verification_status = EXCLUDED.verification_status
            RETURNING compliance_finding_id
        """)
        evidence_query = text("""
            INSERT INTO demooc28.compliance_finding_evidence (
                compliance_finding_id,
                evidence_type,
                evidence_record_id,
                evidence_summary,
                evidence_metadata
            )
            SELECT
                :compliance_finding_id,
                'COLUMN_CLASSIFICATION',
                :classification_id,
                'HIPAA evaluation used a provisional PHI classification.',
                CAST(:evidence_metadata AS jsonb)
            WHERE NOT EXISTS (
                SELECT 1
                FROM demooc28.compliance_finding_evidence
                WHERE compliance_finding_id = :compliance_finding_id
                  AND evidence_type = 'COLUMN_CLASSIFICATION'
                  AND evidence_record_id = :classification_id
            )
        """)
        score_query = text("""
            INSERT INTO demooc28.compliance_scores (
                assessment_id,
                score,
                risk_band,
                scoring_method,
                evidence_coverage,
                applicable_controls,
                assessed_controls,
                status_counts,
                score_metadata
            ) VALUES (
                :assessment_id,
                :score,
                :risk_band,
                'LEGACY_HIPAA_INTERNAL_POLICY',
                :evidence_coverage,
                :applicable_controls,
                :assessed_controls,
                CAST(:status_counts AS jsonb),
                CAST(:score_metadata AS jsonb)
            )
            ON CONFLICT (assessment_id) DO UPDATE SET
                score = EXCLUDED.score,
                risk_band = EXCLUDED.risk_band,
                scoring_method = EXCLUDED.scoring_method,
                evidence_coverage = EXCLUDED.evidence_coverage,
                applicable_controls = EXCLUDED.applicable_controls,
                assessed_controls = EXCLUDED.assessed_controls,
                status_counts = EXCLUDED.status_counts,
                score_metadata = EXCLUDED.score_metadata,
                calculated_at = CURRENT_TIMESTAMP
            RETURNING compliance_score_id
        """)

        with self.database.connect() as connection:
            framework = connection.execute(
                framework_query
            ).mappings().one_or_none()
            if framework is None:
                raise ValueError(
                    "An active, available HIPAA policy-pack version was not found"
                )
            assessment_id = int(connection.execute(
                assessment_query,
                {
                    "run_id": str(run_id),
                    "framework_id": framework["framework_id"],
                    "policy_pack_version_id": framework[
                        "policy_pack_version_id"
                    ],
                },
            ).scalar_one())

            generic_status_counts = {
                "PASS": 0,
                "FAIL": 0,
                "PARTIAL": 0,
                "INSUFFICIENT_EVIDENCE": 0,
                "MANUAL_REVIEW_REQUIRED": 0,
                "NOT_APPLICABLE": 0,
                "NOT_ASSESSED": 0,
            }
            generic_finding_ids: list[int] = []
            for finding in hipaa_findings:
                raw_severity = finding.get("severity")
                severity = str(getattr(raw_severity, "value", raw_severity) or "").strip().upper()
                assessment_status = (
                    "PASS"
                    if severity == "GOOD"
                    else "INSUFFICIENT_EVIDENCE"
                )
                generic_status_counts[assessment_status] += 1
                generic_finding_id = int(connection.execute(
                    finding_query,
                    {
                        "assessment_id": assessment_id,
                        "classification_id": finding["classification_id"],
                        "severity": severity,
                        "assessment_status": assessment_status,
                        "finding": finding["finding"],
                        "recommendation": finding["recommendation"],
                        "confidence": finding["confidence"],
                        "needs_human_review": finding.get(
                            "needs_human_review", False
                        ),
                        "review_reason": finding.get("review_reason"),
                        "verification_status": finding.get(
                            "verification_status", "PROVISIONAL"
                        ),
                        "source_finding_id": finding["finding_id"],
                    },
                ).scalar_one())
                generic_finding_ids.append(generic_finding_id)
                connection.execute(
                    evidence_query,
                    {
                        "compliance_finding_id": generic_finding_id,
                        "classification_id": finding["classification_id"],
                        "evidence_metadata": json.dumps({
                            "source": "column_classifications",
                            "evidence_mode": "PROVISIONAL_CLASSIFICATION",
                        }),
                    },
                )

            phi_count = int(score_payload.get("phi_columns_checked", 0))
            if phi_count == 0:
                generic_status_counts["NOT_APPLICABLE"] = 1
            score_id = int(connection.execute(
                score_query,
                {
                    "assessment_id": assessment_id,
                    "score": score_payload.get("score"),
                    "risk_band": score_payload["risk_band"],
                    # Classification evidence exists, but safeguard-control
                    # evidence is not yet collected by the current HIPAA agent.
                    "evidence_coverage": 0.0,
                    "applicable_controls": phi_count,
                    "assessed_controls": phi_count,
                    "status_counts": json.dumps(generic_status_counts),
                    "score_metadata": json.dumps({
                        "legacy_policy_version": score_payload[
                            "policy_version"
                        ],
                        "severity_counts": score_payload[
                            "severity_counts"
                        ],
                        "provisional": True,
                        "score_label": "INTERNAL_ASSESSMENT_SCORE",
                    }),
                },
            ).scalar_one())

        return {
            "assessment_id": assessment_id,
            "finding_ids": generic_finding_ids,
            "score_id": score_id,
        }

    def create_datasource_connection(
        self,
        connection_name: str,
        database_type: str,
        host: str,
        port: int,
        database_name: str,
        schema_name: str | None,
        username: str,
        password: str,
        encryption_key: str,
        ssl_enabled: bool,
        created_by: str | None = None,
    ) -> dict[str, Any]:
        """Save datasource metadata and an encrypted source password."""
        query = text("""
            INSERT INTO demooc28.datasource_connections (
                connection_name, database_type, host, port, database_name,
                schema_name, username, ssl_enabled, credential_reference,
                password_encrypted, is_active, discovery_status, created_by
            ) VALUES (
                :connection_name, :database_type, :host, :port,
                :database_name, :schema_name, :username, :ssl_enabled, NULL,
                demooc28.pgp_sym_encrypt(
                    CAST(:password AS TEXT),
                    CAST(:encryption_key AS TEXT)
                ),
                TRUE, 'NOT_STARTED', :created_by
            )
            RETURNING connection_id, connection_name, database_type, host,
                      port, database_name, schema_name, username, ssl_enabled,
                      is_active, discovery_status, last_discovered_at,
                      created_at, updated_at
        """)
        with self.database.connect() as connection:
            row = connection.execute(
                query,
                {
                    "connection_name": connection_name,
                    "database_type": database_type,
                    "host": host,
                    "port": port,
                    "database_name": database_name,
                    "schema_name": schema_name,
                    "username": username,
                    "password": password,
                    "encryption_key": encryption_key,
                    "ssl_enabled": ssl_enabled,
                    "created_by": created_by,
                },
            ).mappings().one()
        return dict(row)

    def get_datasource_password(
        self,
        connection_id: int,
        encryption_key: str,
    ) -> str | None:
        """Decrypt a source password for internal connector use only."""
        query = text("""
            SELECT demooc28.pgp_sym_decrypt(
                password_encrypted,
                CAST(:encryption_key AS TEXT)
            ) AS source_password
            FROM demooc28.datasource_connections
            WHERE connection_id = :connection_id
              AND password_encrypted IS NOT NULL
        """)
        with self.database.connect() as connection:
            password = connection.execute(query, {
                "connection_id": connection_id,
                "encryption_key": encryption_key,
            }).scalar_one_or_none()
        return str(password) if password is not None else None

    def update_datasource_password(
        self,
        connection_id: int,
        password: str,
        encryption_key: str,
    ) -> bool:
        """Replace the encrypted source password for one datasource."""
        query = text("""
            UPDATE demooc28.datasource_connections
            SET password_encrypted = demooc28.pgp_sym_encrypt(
                CAST(:password AS TEXT),
                CAST(:encryption_key AS TEXT)
            )
            WHERE connection_id = :connection_id
        """)
        with self.database.connect() as connection:
            result = connection.execute(query, {
                "connection_id": connection_id,
                "password": password,
                "encryption_key": encryption_key,
            })
        return result.rowcount > 0

    def list_datasource_connections(self) -> list[dict[str, Any]]:
        query = text("""
            SELECT connection_id, connection_name, database_type, host, port,
                   database_name, schema_name, username, ssl_enabled, is_active,
                   discovery_status, last_discovered_at, created_at, updated_at
            FROM demooc28.datasource_connections
            ORDER BY created_at DESC
        """)
        with self.database.connect() as connection:
            rows = connection.execute(query).mappings().all()
        return [dict(row) for row in rows]

    def update_datasource_connection(
        self,
        connection_id: int,
        **values: Any,
    ) -> dict[str, Any] | None:
        allowed = {
            "connection_name",
            "host",
            "port",
            "database_name",
            "schema_name",
            "username",
            "ssl_enabled",
        }
        updates = {
            key: value
            for key, value in values.items()
            if key in allowed and value is not None
        }
        if not updates:
            return self.get_datasource_connection(connection_id)
        assignments = ", ".join(
            f"{key} = :{key}" for key in updates
        )
        query = text(f"""
            UPDATE demooc28.datasource_connections
            SET {assignments}
            WHERE connection_id = :connection_id
            RETURNING connection_id, connection_name, database_type, host,
                      port, database_name, schema_name, username, ssl_enabled,
                      is_active, discovery_status, last_discovered_at,
                      created_at, updated_at
        """)
        updates["connection_id"] = connection_id
        with self.database.connect() as connection:
            row = connection.execute(
                query,
                updates,
            ).mappings().one_or_none()
        return dict(row) if row else None

    def deactivate_datasource_connection(self, connection_id: int) -> bool:
        query = text("""
            UPDATE demooc28.datasource_connections
            SET is_active = FALSE
            WHERE connection_id = :connection_id AND is_active = TRUE
        """)
        with self.database.connect() as connection:
            result = connection.execute(query, {"connection_id": connection_id})
        return result.rowcount > 0

    def get_overview(self, run_id: UUID | str) -> dict[str, Any]:
        base_query = text("""
            SELECT
              (SELECT COUNT(*) FROM demooc28.discovered_objects
               WHERE discovery_run_id = CAST(:run_id AS UUID)
                 AND object_type = 'TABLE') AS tables_scanned,
              (SELECT COUNT(*) FROM demooc28.discovered_columns
               WHERE discovery_run_id = CAST(:run_id AS UUID)) AS total_columns,
              (SELECT COUNT(*) FROM demooc28.dependency_edges
               WHERE discovery_run_id = CAST(:run_id AS UUID)) AS dependency_count,
              (SELECT COUNT(*) FROM demooc28.column_classifications
               WHERE discovery_run_id = CAST(:run_id AS UUID)
                 AND needs_human_review = TRUE)
                 AS classifications_needing_review,
              (SELECT COUNT(*) FROM demooc28.hipaa_findings
               WHERE discovery_run_id = CAST(:run_id AS UUID)
                 AND needs_human_review = TRUE)
                 AS hipaa_findings_needing_review
        """)
        classification_query = text("""
            SELECT display_classification, COUNT(*) AS classification_count
            FROM demooc28.column_classifications
            WHERE discovery_run_id = CAST(:run_id AS UUID)
            GROUP BY display_classification
        """)
        score_query = text("""
            SELECT score, risk_band, phi_columns_checked, severity_counts,
                   policy_version, calculated_at
            FROM demooc28.hipaa_scores
            WHERE discovery_run_id = CAST(:run_id AS UUID)
        """)
        params = {"run_id": str(run_id)}
        with self.database.connect() as connection:
            base = dict(connection.execute(base_query, params).mappings().one())
            classifications = connection.execute(
                classification_query, params
            ).mappings().all()
            score = connection.execute(
                score_query, params
            ).mappings().one_or_none()
        counts = {
            key: 0 for key in ("PUBLIC", "PII", "PHI", "FINANCIAL", "SENSITIVE")
        }
        for row in classifications:
            counts[row["display_classification"]] = int(row["classification_count"])
        return {
            **base,
            "classification_counts": counts,
            "hipaa_score": dict(score) if score else None,
        }

    def get_table_profiles_result(
        self, run_id: UUID | str
    ) -> list[dict[str, Any]]:
        query = text("""
            SELECT obj.object_id, obj.schema_name,
                   obj.object_name AS table_name, obj.object_type,
                   prof.table_profile_id, prof.row_count, prof.column_count,
                   prof.average_null_percentage, prof.profiling_method,
                   prof.profile_metadata, prof.created_at, prof.updated_at
            FROM demooc28.discovered_objects AS obj
            JOIN demooc28.table_profiles AS prof
              ON prof.object_id = obj.object_id
             AND prof.discovery_run_id = obj.discovery_run_id
            WHERE obj.discovery_run_id = CAST(:run_id AS UUID)
            ORDER BY obj.schema_name, obj.object_name
        """)
        with self.database.connect() as connection:
            rows = connection.execute(
                query, {"run_id": str(run_id)}
            ).mappings().all()
        return [dict(row) for row in rows]

    def get_classifications_result(
        self, run_id: UUID | str
    ) -> list[dict[str, Any]]:
        query = text("""
            SELECT cls.*, obj.object_id, obj.schema_name,
                   obj.object_name AS table_name, col.column_name,
                   col.ordinal_position, col.data_type, col.nullable,
                   col.is_primary_key, col.is_foreign_key
            FROM demooc28.column_classifications AS cls
            JOIN demooc28.discovered_columns AS col
              ON col.column_id = cls.column_id
            JOIN demooc28.discovered_objects AS obj
              ON obj.object_id = col.object_id
            WHERE cls.discovery_run_id = CAST(:run_id AS UUID)
            ORDER BY obj.schema_name, obj.object_name,
                     col.ordinal_position, col.column_name
        """)
        with self.database.connect() as connection:
            rows = connection.execute(
                query, {"run_id": str(run_id)}
            ).mappings().all()
        return [dict(row) for row in rows]

    def get_dependencies_result(
        self, run_id: UUID | str, object_id: int | None = None
    ) -> list[dict[str, Any]]:
        focused = ""
        if object_id is not None:
            focused = """
              AND (edge.source_object_id = :object_id
                   OR edge.target_object_id = :object_id)
            """
        query = text(f"""
            SELECT edge.*, source.schema_name AS source_schema,
                   source.object_name AS source_object,
                   source.object_type AS source_object_type,
                   target.schema_name AS target_schema,
                   target.object_name AS target_object,
                   target.object_type AS target_object_type
            FROM demooc28.dependency_edges AS edge
            JOIN demooc28.discovered_objects AS source
              ON source.object_id = edge.source_object_id
            JOIN demooc28.discovered_objects AS target
              ON target.object_id = edge.target_object_id
            WHERE edge.discovery_run_id = CAST(:run_id AS UUID)
            {focused}
            ORDER BY source.schema_name, source.object_name,
                     target.schema_name, target.object_name,
                     edge.relationship_type
        """)
        params: dict[str, Any] = {"run_id": str(run_id)}
        if object_id is not None:
            params["object_id"] = object_id
        with self.database.connect() as connection:
            rows = connection.execute(query, params).mappings().all()
        return [dict(row) for row in rows]

    def upsert_control_evidence(
        self,
        assessment_id: int,
        control_code: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        """Save one user attestation and recalculate the assessment."""
        control_query = text("""
            SELECT control_result_id, assessment_id, control_code
            FROM demooc28.compliance_control_results
            WHERE assessment_id = :assessment_id
              AND control_code = :control_code
        """)
        upsert_query = text("""
            INSERT INTO demooc28.compliance_control_evidence (
                assessment_id, control_result_id, evidence_source,
                verification_status, verification_date, explanation,
                internal_reference
            ) VALUES (
                :assessment_id, :control_result_id, 'USER_ATTESTATION',
                :verification_status, :verification_date, :explanation,
                :internal_reference
            )
            ON CONFLICT (control_result_id) DO UPDATE SET
                verification_status = EXCLUDED.verification_status,
                verification_date = EXCLUDED.verification_date,
                explanation = EXCLUDED.explanation,
                internal_reference = EXCLUDED.internal_reference,
                evidence_source = 'USER_ATTESTATION'
            RETURNING control_evidence_id, assessment_id, control_result_id,
                      evidence_source, verification_status, verification_date,
                      explanation, internal_reference, created_at, updated_at
        """)
        status_mapping = {
            "CONFIRMED": ("PASS", "GOOD", False),
            "NOT_CONFIRMED": ("FAIL", "CRITICAL", True),
            "NOT_SURE": ("INSUFFICIENT_EVIDENCE", "NEEDS_REVIEW", True),
        }
        status, severity, review = status_mapping[
            payload["verification_status"]
        ]
        update_control_query = text("""
            UPDATE demooc28.compliance_control_results
            SET assessment_status = :assessment_status,
                severity = :severity,
                explanation = :explanation,
                confidence = 1.0,
                needs_human_review = :needs_human_review
            WHERE control_result_id = :control_result_id
        """)
        with self.database.connect() as connection:
            control = connection.execute(
                control_query,
                {
                    "assessment_id": assessment_id,
                    "control_code": control_code,
                },
            ).mappings().one_or_none()
            if control is None:
                raise ValueError("Compliance control was not found")
            evidence = dict(connection.execute(
                upsert_query,
                {
                    "assessment_id": assessment_id,
                    "control_result_id": control["control_result_id"],
                    "verification_status": payload["verification_status"],
                    "verification_date": payload.get("verification_date"),
                    "explanation": payload["explanation"],
                    "internal_reference": payload.get("internal_reference"),
                },
            ).mappings().one())
            connection.execute(
                update_control_query,
                {
                    "assessment_status": status,
                    "severity": severity,
                    "explanation": (
                        "User attestation: " + payload["explanation"]
                    ),
                    "needs_human_review": review,
                    "control_result_id": control["control_result_id"],
                },
            )
        self.recalculate_compliance_score(assessment_id)
        evidence["control_code"] = control_code
        return evidence

    def list_control_evidence(
        self, assessment_id: int
    ) -> list[dict[str, Any]]:
        query = text("""
            SELECT evidence.control_evidence_id, evidence.assessment_id,
                   evidence.control_result_id, result.control_code,
                   evidence.evidence_source, evidence.verification_status,
                   evidence.verification_date, evidence.explanation,
                   evidence.internal_reference, evidence.created_at,
                   evidence.updated_at
            FROM demooc28.compliance_control_evidence AS evidence
            JOIN demooc28.compliance_control_results AS result
              ON result.control_result_id = evidence.control_result_id
            WHERE evidence.assessment_id = :assessment_id
            ORDER BY result.control_code
        """)
        with self.database.connect() as connection:
            rows = connection.execute(
                query, {"assessment_id": assessment_id}
            ).mappings().all()
        return [dict(row) for row in rows]

    def recalculate_compliance_score(
        self, assessment_id: int
    ) -> dict[str, Any]:
        """Recalculate equal-weight score and evidence coverage."""
        controls_query = text("""
            SELECT assessment_status
            FROM demooc28.compliance_control_results
            WHERE assessment_id = :assessment_id
        """)
        score_query = text("""
            UPDATE demooc28.compliance_scores
            SET score = :score,
                risk_band = :risk_band,
                scoring_method = 'EVIDENCE_BASED_EQUAL_WEIGHT',
                evidence_coverage = :evidence_coverage,
                applicable_controls = :applicable_controls,
                assessed_controls = :assessed_controls,
                status_counts = CAST(:status_counts AS jsonb),
                score_metadata = score_metadata || CAST(:metadata AS jsonb),
                calculated_at = CURRENT_TIMESTAMP
            WHERE assessment_id = :assessment_id
            RETURNING compliance_score_id, score, risk_band,
                      evidence_coverage, applicable_controls,
                      assessed_controls, status_counts, score_metadata,
                      calculated_at
        """)
        statuses = (
            "PASS", "FAIL", "PARTIAL", "INSUFFICIENT_EVIDENCE",
            "MANUAL_REVIEW_REQUIRED", "NOT_APPLICABLE", "NOT_ASSESSED",
        )
        with self.database.connect() as connection:
            rows = connection.execute(
                controls_query, {"assessment_id": assessment_id}
            ).mappings().all()
            if not rows:
                raise ValueError("Compliance assessment has no controls")
            values = [row["assessment_status"] for row in rows]
            counts = {status: values.count(status) for status in statuses}
            applicable = sum(
                count for status, count in counts.items()
                if status != "NOT_APPLICABLE"
            )
            assessed = sum(
                counts[status] for status in ("PASS", "PARTIAL", "FAIL")
            )
            coverage = round(100 * assessed / applicable, 2) if applicable else 100.0
            if not applicable:
                score = None
                risk_band = "NOT_APPLICABLE"
            elif coverage < 50:
                score = None
                risk_band = "INSUFFICIENT_EVIDENCE"
            else:
                score = round(
                    (counts["PASS"] * 100 + counts["PARTIAL"] * 50)
                    / assessed,
                    2,
                )
                risk_band = (
                    "GOOD" if score >= 85
                    else "NEEDS_REVIEW" if score >= 60
                    else "SERIOUS" if score >= 30
                    else "CRITICAL"
                )
            row = connection.execute(
                score_query,
                {
                    "assessment_id": assessment_id,
                    "score": score,
                    "risk_band": risk_band,
                    "evidence_coverage": coverage,
                    "applicable_controls": applicable,
                    "assessed_controls": assessed,
                    "status_counts": json.dumps(counts),
                    "metadata": json.dumps({
                        "minimum_evidence_coverage": 50,
                        "weights": "EQUAL",
                        "score_label": "INTERNAL_ASSESSMENT_SCORE",
                    }),
                },
            ).mappings().one_or_none()
            if row is None:
                raise ValueError("Compliance score record was not found")
        return dict(row)

    def get_compliance_results(
        self,
        run_id: UUID | str,
    ) -> list[dict[str, Any]]:
        """Return separate generic results for all frameworks in one run."""
        assessments_query = text("""
            SELECT
                assessment.assessment_id,
                framework.framework_code,
                framework.framework_name,
                policy.version AS policy_version,
                assessment.status,
                score.score,
                score.risk_band,
                score.scoring_method,
                score.evidence_coverage,
                score.applicable_controls,
                score.assessed_controls,
                score.status_counts,
                score.score_metadata,
                score.calculated_at
            FROM demooc28.compliance_assessments AS assessment
            JOIN demooc28.compliance_frameworks AS framework
              ON framework.framework_id = assessment.framework_id
            JOIN demooc28.policy_pack_versions AS policy
              ON policy.policy_pack_version_id =
                 assessment.policy_pack_version_id
            LEFT JOIN demooc28.compliance_scores AS score
              ON score.assessment_id = assessment.assessment_id
            WHERE assessment.discovery_run_id = CAST(:run_id AS UUID)
            ORDER BY framework.framework_name
        """)
        controls_query = text("""
            SELECT result.*, assessment.assessment_id,
                   evidence.control_evidence_id,
                   evidence.evidence_source,
                   evidence.verification_status AS evidence_verification_status,
                   evidence.verification_date,
                   evidence.explanation AS evidence_explanation,
                   evidence.internal_reference
            FROM demooc28.compliance_control_results AS result
            JOIN demooc28.compliance_assessments AS assessment
              ON assessment.assessment_id = result.assessment_id
            LEFT JOIN demooc28.compliance_control_evidence AS evidence
              ON evidence.control_result_id = result.control_result_id
            WHERE assessment.discovery_run_id = CAST(:run_id AS UUID)
            ORDER BY assessment.assessment_id, result.control_code
        """)
        findings_query = text("""
            SELECT
                finding.compliance_finding_id,
                assessment.assessment_id,
                finding.classification_id,
                finding.severity,
                finding.assessment_status,
                finding.finding,
                finding.recommendation,
                finding.confidence,
                finding.needs_human_review,
                finding.review_reason,
                finding.verification_status,
                object.schema_name,
                object.object_name AS table_name,
                column_info.column_name,
                classification.display_classification,
                classification.sensitive_data_type
            FROM demooc28.compliance_findings AS finding
            JOIN demooc28.compliance_assessments AS assessment
              ON assessment.assessment_id = finding.assessment_id
            LEFT JOIN demooc28.column_classifications AS classification
              ON classification.classification_id = finding.classification_id
            LEFT JOIN demooc28.discovered_columns AS column_info
              ON column_info.column_id = classification.column_id
            LEFT JOIN demooc28.discovered_objects AS object
              ON object.object_id = column_info.object_id
            WHERE assessment.discovery_run_id = CAST(:run_id AS UUID)
            ORDER BY assessment.assessment_id, finding.compliance_finding_id
        """)
        params = {"run_id": str(run_id)}
        with self.database.connect() as connection:
            assessments = [
                dict(row)
                for row in connection.execute(
                    assessments_query, params
                ).mappings().all()
            ]
            findings = [
                dict(row)
                for row in connection.execute(
                    findings_query, params
                ).mappings().all()
            ]
            controls = [dict(row) for row in connection.execute(controls_query, params).mappings().all()]
        findings_by_assessment: dict[int, list[dict[str, Any]]] = {}
        for finding in findings:
            findings_by_assessment.setdefault(
                int(finding.pop("assessment_id")), []
            ).append(finding)
        controls_by_assessment: dict[int, list[dict[str, Any]]] = {}
        for control in controls:
            controls_by_assessment.setdefault(int(control.pop("assessment_id")), []).append(control)
        for assessment in assessments:
            assessment_id = int(assessment["assessment_id"])
            assessment["controls"] = controls_by_assessment.get(assessment_id, [])
            assessment["findings"] = findings_by_assessment.get(assessment_id, [])
        return assessments

    def get_hipaa_result(self, run_id: UUID | str) -> dict[str, Any]:
        findings_query = text("""
            SELECT finding.*, obj.object_id, obj.schema_name,
                   obj.object_name AS table_name, col.column_name,
                   cls.display_classification
            FROM demooc28.hipaa_findings AS finding
            JOIN demooc28.column_classifications AS cls
              ON cls.classification_id = finding.classification_id
            JOIN demooc28.discovered_columns AS col
              ON col.column_id = cls.column_id
            JOIN demooc28.discovered_objects AS obj
              ON obj.object_id = col.object_id
            WHERE finding.discovery_run_id = CAST(:run_id AS UUID)
            ORDER BY finding.severity, obj.schema_name,
                     obj.object_name, col.column_name
        """)
        score_query = text("""
            SELECT * FROM demooc28.hipaa_scores
            WHERE discovery_run_id = CAST(:run_id AS UUID)
        """)
        params = {"run_id": str(run_id)}
        with self.database.connect() as connection:
            findings = connection.execute(
                findings_query, params
            ).mappings().all()
            score = connection.execute(
                score_query, params
            ).mappings().one_or_none()
        return {
            "score": dict(score) if score else None,
            "findings": [dict(row) for row in findings],
        }

    def get_run_stages(
        self,
        run_id: UUID | str,
    ) -> list[dict[str, Any]]:
        """Return all progress stages for one discovery run."""
        query = text("""
            SELECT
                stage_id,
                discovery_run_id,
                stage_name,
                stage_status,
                processed_items,
                total_items,
                attempt_number,
                message,
                error_code,
                error_message,
                started_at,
                completed_at,
                created_at,
                updated_at
            FROM demooc28.discovery_run_stages
            WHERE discovery_run_id = :run_id
            ORDER BY stage_id
        """)

        with self.database.connect() as connection:
            rows = connection.execute(
                query,
                {"run_id": str(run_id)},
            ).mappings().all()

        return [dict(row) for row in rows]
