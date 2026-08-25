from __future__ import annotations

import json
from typing import Any
from uuid import UUID

from sqlalchemy import text

from src.services.database import MetadataDatabase


DISCOVERY_STAGES = [
    "CONNECTION_VALIDATION",
    "METADATA_PROFILING",
    "COLUMN_CLASSIFICATION",
    "DEPENDENCY_MAPPING",
    "HIPAA_COMPLIANCE",
    "REPORT_FINALIZATION",
]


class DiscoveryRepository:
    def __init__(self, database: MetadataDatabase):
        self.database = database

    def create_run(
        self,
        run_id: UUID,
        connection_id: int,
        requested_scopes: list[str],
        effective_scopes: list[str] | None = None,
    ) -> None:
        effective_scopes = effective_scopes or requested_scopes
        query = text("""
            INSERT INTO demooc28.discovery_runs (
                discovery_run_id, connection_id, requested_scopes,
                effective_scopes, status, progress_percentage
            ) VALUES (
                :run_id, :connection_id,
                CAST(:requested_scopes AS jsonb),
                CAST(:effective_scopes AS jsonb),
                'PENDING', 0
            )
        """)
        with self.database.connect() as connection:
            connection.execute(query, {
                "run_id": str(run_id),
                "connection_id": connection_id,
                "requested_scopes": json.dumps(requested_scopes),
                "effective_scopes": json.dumps(effective_scopes),
            })

    def create_run_stages(self, run_id: UUID, effective_scopes: list[str]) -> None:
        effective_scope_set = set(effective_scopes)
        stage_scope_mapping = {
            "COLUMN_CLASSIFICATION": "COLUMN_CLASSIFICATION",
            "DEPENDENCY_MAPPING": "DEPENDENCY_MAP",
            "HIPAA_COMPLIANCE": "HIPAA_COMPLIANCE",
        }
        query = text("""
            INSERT INTO demooc28.discovery_run_stages (
                discovery_run_id, stage_name, stage_status, message
            ) VALUES (
                :run_id, :stage_name, :stage_status, :message
            )
            ON CONFLICT (discovery_run_id, stage_name) DO NOTHING
        """)
        with self.database.connect() as connection:
            for stage_name in DISCOVERY_STAGES:
                required_scope = stage_scope_mapping.get(stage_name)
                if required_scope and required_scope not in effective_scope_set:
                    stage_status = "SKIPPED"
                    message = "Stage not requested"
                else:
                    stage_status = "PENDING"
                    message = "Waiting to start"
                connection.execute(query, {
                    "run_id": str(run_id),
                    "stage_name": stage_name,
                    "stage_status": stage_status,
                    "message": message,
                })

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
        query = text(
            """
            SELECT
                datasource.connection_id,
                datasource.connection_name,
                datasource.database_type,
                datasource.host,
                datasource.port,
                datasource.database_name,
                datasource.username,
                datasource.ssl_enabled,
                datasource.is_active,
                datasource.discovery_status
            FROM demooc28.discovery_runs AS discovery_run
            JOIN demooc28.datasource_connections AS datasource
              ON datasource.connection_id = discovery_run.connection_id
            WHERE discovery_run.discovery_run_id = CAST(:run_id AS UUID)
            """
        )
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


    def create_datasource_connection(
        self,
        connection_name: str,
        database_type: str,
        host: str,
        port: int,
        database_name: str,
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
                username, ssl_enabled, credential_reference,
                password_encrypted, is_active, discovery_status, created_by
            ) VALUES (
                :connection_name, :database_type, :host, :port,
                :database_name, :username, :ssl_enabled, NULL,
                demooc28.pgp_sym_encrypt(
                    CAST(:password AS TEXT),
                    CAST(:encryption_key AS TEXT)
                ),
                TRUE, 'NOT_STARTED', :created_by
            )
            RETURNING connection_id, connection_name, database_type, host,
                      port, database_name, username, ssl_enabled, is_active,
                      discovery_status, last_discovered_at, created_at,
                      updated_at
        """)
        with self.database.connect() as connection:
            row = connection.execute(query, {
                "connection_name": connection_name,
                "database_type": database_type,
                "host": host,
                "port": port,
                "database_name": database_name,
                "username": username,
                "password": password,
                "encryption_key": encryption_key,
                "ssl_enabled": ssl_enabled,
                "created_by": created_by,
            }).mappings().one()
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
                   database_name, username, ssl_enabled, is_active,
                   discovery_status, last_discovered_at, created_at, updated_at
            FROM demooc28.datasource_connections
            ORDER BY created_at DESC
        """)
        with self.database.connect() as connection:
            rows = connection.execute(query).mappings().all()
        return [dict(row) for row in rows]

    def update_datasource_connection(
        self, connection_id: int, **values: Any
    ) -> dict[str, Any] | None:
        allowed = {
            "connection_name", "host", "port", "database_name",
            "username", "ssl_enabled",
        }
        updates = {
            key: value for key, value in values.items()
            if key in allowed and value is not None
        }
        if not updates:
            return self.get_datasource_connection(connection_id)
        assignments = ", ".join(f"{key} = :{key}" for key in updates)
        query = text(f"""
            UPDATE demooc28.datasource_connections
            SET {assignments}
            WHERE connection_id = :connection_id
            RETURNING connection_id, connection_name, database_type, host,
                      port, database_name, username, ssl_enabled, is_active,
                      discovery_status, last_discovered_at, created_at,
                      updated_at
        """)
        updates["connection_id"] = connection_id
        with self.database.connect() as connection:
            row = connection.execute(query, updates).mappings().one_or_none()
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
