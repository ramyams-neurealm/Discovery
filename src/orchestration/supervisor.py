from __future__ import annotations

from typing import Any

from langgraph.graph import END, START, StateGraph

from src.orchestration.state import DiscoveryState
from src.repositories.discovery_repository import DiscoveryRepository


class DiscoverySupervisor:
    def __init__(
        self,
        metadata_agent,
        classification_agent,
        dependency_agent,
        hipaa_agent,
        report_agent,
        repository: DiscoveryRepository,
    ):
        self.metadata_agent = metadata_agent
        self.classification_agent = classification_agent
        self.dependency_agent = dependency_agent
        self.hipaa_agent = hipaa_agent
        self.report_agent = report_agent
        self.repository = repository
        self.graph = self._build_graph()

    def _metadata(self, state: DiscoveryState) -> DiscoveryState:
        output = self.metadata_agent.run(
            run_id=state["discovery_run_id"],
            connection_id=state["connection_id"],
            source_connection=state["source_connection"],
        )
        return {**state, **output, "status": "RUNNING"}

    def _classify(self, state: DiscoveryState) -> DiscoveryState:
        run_id = state["discovery_run_id"]

        if "COLUMN_CLASSIFICATION" not in state["effective_scopes"]:
            return state

        self.repository.update_run_status(
            run_id=run_id,
            status="RUNNING",
            current_stage="COLUMN_CLASSIFICATION",
            progress_percentage=40,
        )
        self.repository.update_stage(
            run_id=run_id,
            stage_name="COLUMN_CLASSIFICATION",
            stage_status="RUNNING",
            message="Classifying discovered columns",
        )

        column_profiles = state.get("column_profiles", [])
        results = []

        try:
            for profile in column_profiles:
                payload = {
                    "object_id": profile["object_id"],
                    "schema_name": profile["schema_name"],
                    "table_name": profile["table_name"],
                    "column_name": profile["column_name"],
                    "data_type": profile["data_type"],
                    "nullable": profile.get("nullable"),
                    "is_primary_key": profile.get(
                        "is_primary_key", False
                    ),
                    "is_foreign_key": profile.get(
                        "is_foreign_key", False
                    ),
                    "neighboring_columns": profile.get(
                        "neighboring_columns", []
                    ),
                    "masked_samples": profile.get(
                        "masked_samples", []
                    ),
                }
                results.append(
                    self.classification_agent.classify(payload)
                )

            column_ids_by_key = {
                (
                    profile["schema_name"],
                    profile["table_name"],
                    profile["column_name"],
                ): profile["column_id"]
                for profile in column_profiles
            }

            saved_records = self.repository.save_classifications(
                run_id=run_id,
                results=results,
                column_ids_by_key=column_ids_by_key,
            )

            self.repository.update_stage(
                run_id=run_id,
                stage_name="COLUMN_CLASSIFICATION",
                stage_status="COMPLETED",
                message=f"Classified {len(results)} columns",
                processed_items=len(results),
                total_items=len(column_profiles),
            )
            self.repository.update_run_status(
                run_id=run_id,
                status="RUNNING",
                current_stage="COLUMN_CLASSIFICATION",
                progress_percentage=60,
            )

            return {
                **state,
                "classifications": results,
                "classification_records": saved_records,
            }

        except Exception as error:
            safe_error = (
                "Column classification failed: "
                f"{error.__class__.__name__}"
            )
            self.repository.update_stage(
                run_id=run_id,
                stage_name="COLUMN_CLASSIFICATION",
                stage_status="FAILED",
                message="Column classification failed",
                error_code="CLASSIFICATION_FAILED",
                error_message=safe_error,
            )
            self.repository.update_run_status(
                run_id=run_id,
                status="FAILED",
                current_stage="COLUMN_CLASSIFICATION",
                progress_percentage=40,
                error_code="CLASSIFICATION_FAILED",
                error_message=safe_error,
            )
            raise

    def _dependencies(self, state: DiscoveryState) -> DiscoveryState:
        run_id = state["discovery_run_id"]
        if "DEPENDENCY_MAP" not in state["effective_scopes"]:
            return state

        self.repository.update_run_status(
            run_id=run_id,
            status="RUNNING",
            current_stage="DEPENDENCY_MAPPING",
            progress_percentage=65,
        )
        self.repository.update_stage(
            run_id=run_id,
            stage_name="DEPENDENCY_MAPPING",
            stage_status="RUNNING",
            message="Mapping database dependencies",
        )

        try:
            dependencies = self.dependency_agent.run(
                state.get("objects", [])
            )
            saved_dependencies = self.repository.save_dependencies(
                run_id=run_id,
                edges=dependencies,
                objects=state.get("objects", []),
            )
            self.repository.update_stage(
                run_id=run_id,
                stage_name="DEPENDENCY_MAPPING",
                stage_status="COMPLETED",
                message=f"Mapped {len(dependencies)} dependencies",
                processed_items=len(dependencies),
                total_items=len(dependencies),
            )
            self.repository.update_run_status(
                run_id=run_id,
                status="RUNNING",
                current_stage="DEPENDENCY_MAPPING",
                progress_percentage=75,
            )
            return {
                **state,
                "dependencies": dependencies,
                "dependency_records": saved_dependencies,
            }
        except Exception as error:
            safe_error = (
                "Dependency mapping failed: "
                f"{error.__class__.__name__}"
            )
            self.repository.update_stage(
                run_id=run_id,
                stage_name="DEPENDENCY_MAPPING",
                stage_status="FAILED",
                message="Dependency mapping failed",
                error_code="DEPENDENCY_MAPPING_FAILED",
                error_message=safe_error,
            )
            self.repository.update_run_status(
                run_id=run_id,
                status="FAILED",
                current_stage="DEPENDENCY_MAPPING",
                progress_percentage=65,
                error_code="DEPENDENCY_MAPPING_FAILED",
                error_message=safe_error,
            )
            raise

    def _hipaa(self, state: DiscoveryState) -> DiscoveryState:
        run_id = state["discovery_run_id"]
        if "HIPAA_COMPLIANCE" not in state["effective_scopes"]:
            return state

        self.repository.update_run_status(
            run_id=run_id,
            status="RUNNING",
            current_stage="HIPAA_COMPLIANCE",
            progress_percentage=78,
        )
        self.repository.update_stage(
            run_id=run_id,
            stage_name="HIPAA_COMPLIANCE",
            stage_status="RUNNING",
            message="Evaluating HIPAA findings for PHI columns",
        )

        try:
            findings, score = self.hipaa_agent.evaluate(
                state.get("classifications", [])
            )
            saved_findings = self.repository.save_hipaa_findings(
                run_id=run_id,
                findings=findings,
                classification_records=state.get(
                    "classification_records", []
                ),
            )
            score_id = self.repository.save_hipaa_score(
                run_id=run_id,
                score=score,
            )
            self.repository.update_stage(
                run_id=run_id,
                stage_name="HIPAA_COMPLIANCE",
                stage_status="COMPLETED",
                message=(
                    f"Evaluated {score.phi_columns_checked} PHI columns"
                ),
                processed_items=score.phi_columns_checked,
                total_items=score.phi_columns_checked,
            )
            self.repository.update_run_status(
                run_id=run_id,
                status="RUNNING",
                current_stage="HIPAA_COMPLIANCE",
                progress_percentage=90,
            )
            return {
                **state,
                "hipaa_findings": findings,
                "hipaa_finding_records": saved_findings,
                "hipaa_score": score,
                "hipaa_score_id": score_id,
            }
        except Exception as error:
            safe_error = (
                "HIPAA evaluation failed: "
                f"{error.__class__.__name__}"
            )
            self.repository.update_stage(
                run_id=run_id,
                stage_name="HIPAA_COMPLIANCE",
                stage_status="FAILED",
                message="HIPAA evaluation failed",
                error_code="HIPAA_EVALUATION_FAILED",
                error_message=safe_error,
            )
            self.repository.update_run_status(
                run_id=run_id,
                status="FAILED",
                current_stage="HIPAA_COMPLIANCE",
                progress_percentage=78,
                error_code="HIPAA_EVALUATION_FAILED",
                error_message=safe_error,
            )
            raise

    def _report(self, state: DiscoveryState) -> DiscoveryState:
        run_id = state["discovery_run_id"]
        self.repository.update_run_status(
            run_id=run_id,
            status="RUNNING",
            current_stage="REPORT_FINALIZATION",
            progress_percentage=95,
        )
        self.repository.update_stage(
            run_id=run_id,
            stage_name="REPORT_FINALIZATION",
            stage_status="RUNNING",
            message="Building discovery report",
        )

        report = self.report_agent.build(state)

        self.repository.update_stage(
            run_id=run_id,
            stage_name="REPORT_FINALIZATION",
            stage_status="COMPLETED",
            message="Discovery report completed",
            processed_items=1,
            total_items=1,
        )
        self.repository.update_run_status(
            run_id=run_id,
            status="SUCCEEDED",
            current_stage="REPORT_FINALIZATION",
            progress_percentage=100,
        )
        return {**state, "report": report, "status": "SUCCEEDED"}

    def _build_graph(self):
        graph = StateGraph(DiscoveryState)
        graph.add_node("metadata_and_profiling", self._metadata)
        graph.add_node("classification", self._classify)
        graph.add_node("dependency_mapping", self._dependencies)
        graph.add_node("hipaa", self._hipaa)
        graph.add_node("report", self._report)

        graph.add_edge(START, "metadata_and_profiling")
        graph.add_edge("metadata_and_profiling", "classification")
        graph.add_edge("classification", "dependency_mapping")
        graph.add_edge("dependency_mapping", "hipaa")
        graph.add_edge("hipaa", "report")
        graph.add_edge("report", END)
        return graph.compile()

    def invoke(
        self,
        discovery_run_id: str,
        connection_id: int,
        scopes: list[str],
        source_connection: Any,
    ) -> DiscoveryState:
        effective_scopes = set(scopes)
        if "HIPAA_COMPLIANCE" in effective_scopes:
            effective_scopes.add("COLUMN_CLASSIFICATION")

        initial_state: DiscoveryState = {
            "discovery_run_id": discovery_run_id,
            "connection_id": connection_id,
            "requested_scopes": scopes,
            "effective_scopes": sorted(effective_scopes),
            "source_connection": source_connection,
            "errors": [],
            "status": "PENDING",
        }
        return self.graph.invoke(initial_state)
