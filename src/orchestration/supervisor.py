from __future__ import annotations

from typing import Any

from langgraph.graph import END, START, StateGraph

from src.orchestration.state import DiscoveryState
from src.repositories.discovery_repository import DiscoveryRepository
from src.tools.classification_policy import build_classification_summary, reconcile_linked_identifiers


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
            selected_objects=state.get("selected_objects", []),
        )
        return {**state, **output, "status": "RUNNING"}

    def _classify(self, state: DiscoveryState) -> DiscoveryState:
        run_id = state["discovery_run_id"]
        if "COLUMN_CLASSIFICATION" not in state["effective_scopes"]:
            return state
        self.repository.update_run_status(run_id, "RUNNING", "COLUMN_CLASSIFICATION", 40)
        self.repository.update_stage(run_id, "COLUMN_CLASSIFICATION", "RUNNING", "Classifying discovered columns")
        profiles = state.get("column_profiles", [])
        try:
            results = []
            keys = (
                "object_id", "column_id", "schema_name", "table_name", "column_name",
                "data_type", "nullable", "is_primary_key", "is_foreign_key",
                "neighboring_columns", "masked_samples", "null_percentage", "distinct_count",
            )
            for profile in profiles:
                results.append(self.classification_agent.classify({key: profile.get(key) for key in keys}))
            results = reconcile_linked_identifiers(results, state.get("objects", []))
            summary = build_classification_summary(state.get("objects", []), profiles, results)
            ids = {(p["schema_name"], p["table_name"], p["column_name"]): p["column_id"] for p in profiles}
            saved = self.repository.save_classifications(run_id, results, ids)
            message = (
                f"Classified {summary['classified_columns']} of {summary['discovered_columns']} "
                f"discovered columns; {summary['excluded_columns']} excluded because "
                "they had no eligible table profile."
            )
            self.repository.update_stage(run_id, "COLUMN_CLASSIFICATION", "COMPLETED", message, len(results), summary["eligible_columns"])
            self.repository.update_run_status(run_id, "RUNNING", "COLUMN_CLASSIFICATION", 60)
            return {**state, "classifications": results, "classification_records": saved, "classification_summary": summary}
        except Exception as error:
            safe = f"Column classification failed: {error.__class__.__name__}"
            self.repository.update_stage(run_id, "COLUMN_CLASSIFICATION", "FAILED", "Column classification failed", error_code="CLASSIFICATION_FAILED", error_message=safe)
            self.repository.update_run_status(run_id, "FAILED", "COLUMN_CLASSIFICATION", 40, "CLASSIFICATION_FAILED", safe)
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
        selected_frameworks = set(state.get("selected_frameworks", []))
        legacy_hipaa = "HIPAA_COMPLIANCE" in state["effective_scopes"]
        generic_compliance = (
            "REGULATORY_COMPLIANCE" in state["effective_scopes"]
        )
        if not legacy_hipaa and not generic_compliance:
            return state
        if "HIPAA" not in selected_frameworks:
            return state
        stage_name = (
            "REGULATORY_COMPLIANCE"
            if generic_compliance
            else "HIPAA_COMPLIANCE"
        )

        self.repository.update_run_status(
            run_id=run_id,
            status="RUNNING",
            current_stage=stage_name,
            progress_percentage=78,
        )
        self.repository.update_stage(
            run_id=run_id,
            stage_name=stage_name,
            stage_status="RUNNING",
            message="Evaluating selected compliance policy packs",
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
            generic_hipaa_result = self.repository.save_generic_hipaa_result(
                run_id=run_id, hipaa_findings=saved_findings, hipaa_score=score
            )
            hipaa_control_assessment = self.repository.save_hipaa_control_assessment(
                run_id=run_id, classification_records=state.get("classification_records", [])
            )
            self.repository.update_stage(
                run_id=run_id,
                stage_name=stage_name,
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
                current_stage=stage_name,
                progress_percentage=90,
            )
            return {
                **state,
                "hipaa_findings": findings,
                "hipaa_finding_records": saved_findings,
                "hipaa_score": score,
                "hipaa_score_id": score_id,
                "generic_hipaa_result": generic_hipaa_result,
                "hipaa_control_assessment": hipaa_control_assessment,
            }
        except Exception as error:
            safe_error = (
                "HIPAA evaluation failed: "
                f"{error.__class__.__name__}"
            )
            self.repository.update_stage(
                run_id=run_id,
                stage_name=stage_name,
                stage_status="FAILED",
                message="HIPAA evaluation failed",
                error_code="HIPAA_EVALUATION_FAILED",
                error_message=safe_error,
            )
            self.repository.update_run_status(
                run_id=run_id,
                status="FAILED",
                current_stage=stage_name,
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
        selected_objects: list[dict[str, str]] | None = None,
        selected_frameworks: list[str] | None = None,
    ) -> DiscoveryState:
        effective_scopes = set(scopes)
        if (
            "HIPAA_COMPLIANCE" in effective_scopes
            or "REGULATORY_COMPLIANCE" in effective_scopes
        ):
            effective_scopes.add("COLUMN_CLASSIFICATION")
        framework_codes = list(selected_frameworks or [])
        if (
            "HIPAA_COMPLIANCE" in effective_scopes
            and "HIPAA" not in framework_codes
        ):
            framework_codes.append("HIPAA")

        initial_state: DiscoveryState = {
            "discovery_run_id": discovery_run_id,
            "connection_id": connection_id,
            "requested_scopes": scopes,
            "effective_scopes": sorted(effective_scopes),
            "selected_objects": selected_objects or [],
            "selected_frameworks": framework_codes,
            "source_connection": source_connection,
            "errors": [],
            "status": "PENDING",
        }
        return self.graph.invoke(initial_state)
