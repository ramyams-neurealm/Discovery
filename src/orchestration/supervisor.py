# from __future__ import annotations

# from typing import Any

# from langgraph.graph import END, START, StateGraph

# from src.orchestration.state import DiscoveryState
# from src.repositories.discovery_repository import DiscoveryRepository
# from src.tools.classification_policy import build_classification_summary, reconcile_linked_identifiers
# from src.tools.hipaa_control_policy import evaluate_hipaa_controls
# from src.tools.pci_dss_control_policy import (
#     build_pci_dss_classification_findings,
#     evaluate_pci_dss_controls,
# )


# class DiscoverySupervisor:
#     def __init__(
#         self,
#         metadata_agent,
#         classification_agent,
#         dependency_agent,
#         hipaa_agent,
#         report_agent,
#         repository: DiscoveryRepository,
#     ):
#         self.metadata_agent = metadata_agent
#         self.classification_agent = classification_agent
#         self.dependency_agent = dependency_agent
#         self.hipaa_agent = hipaa_agent
#         self.report_agent = report_agent
#         self.repository = repository
#         self.graph = self._build_graph()

#     def _metadata(self, state: DiscoveryState) -> DiscoveryState:
#         output = self.metadata_agent.run(
#             run_id=state["discovery_run_id"],
#             connection_id=state["connection_id"],
#             source_connection=state["source_connection"],
#             selected_objects=state.get("selected_objects", []),
#         )
#         return {**state, **output, "status": "RUNNING"}

#     def _classify(self, state: DiscoveryState) -> DiscoveryState:
#         run_id = state["discovery_run_id"]
#         if "COLUMN_CLASSIFICATION" not in state["effective_scopes"]:
#             return state
#         self.repository.update_run_status(run_id, "RUNNING", "COLUMN_CLASSIFICATION", 40)
#         self.repository.update_stage(run_id, "COLUMN_CLASSIFICATION", "RUNNING", "Classifying discovered columns")
#         profiles = state.get("column_profiles", [])
#         try:
#             results = []
#             keys = (
#                 "object_id", "column_id", "schema_name", "table_name", "column_name",
#                 "data_type", "nullable", "is_primary_key", "is_foreign_key",
#                 "neighboring_columns", "masked_samples", "null_percentage", "distinct_count",
#             )
#             for profile in profiles:
#                 results.append(self.classification_agent.classify({key: profile.get(key) for key in keys}))
#             results = reconcile_linked_identifiers(results, state.get("objects", []))
#             summary = build_classification_summary(state.get("objects", []), profiles, results)
#             ids = {(p["schema_name"], p["table_name"], p["column_name"]): p["column_id"] for p in profiles}
#             saved = self.repository.save_classifications(run_id, results, ids)
#             message = (
#                 f"Classified {summary['classified_columns']} of {summary['discovered_columns']} "
#                 f"discovered columns; {summary['excluded_columns']} excluded because "
#                 "they had no eligible table profile."
#             )
#             self.repository.update_stage(run_id, "COLUMN_CLASSIFICATION", "COMPLETED", message, len(results), summary["eligible_columns"])
#             self.repository.update_run_status(run_id, "RUNNING", "COLUMN_CLASSIFICATION", 60)
#             return {**state, "classifications": results, "classification_records": saved, "classification_summary": summary}
#         except Exception as error:
#             safe = f"Column classification failed: {error.__class__.__name__}"
#             self.repository.update_stage(run_id, "COLUMN_CLASSIFICATION", "FAILED", "Column classification failed", error_code="CLASSIFICATION_FAILED", error_message=safe)
#             self.repository.update_run_status(run_id, "FAILED", "COLUMN_CLASSIFICATION", 40, "CLASSIFICATION_FAILED", safe)
#             raise
#     def _dependencies(self, state: DiscoveryState) -> DiscoveryState:
#         run_id = state["discovery_run_id"]
#         if "DEPENDENCY_MAP" not in state["effective_scopes"]:
#             return state

#         self.repository.update_run_status(
#             run_id=run_id,
#             status="RUNNING",
#             current_stage="DEPENDENCY_MAPPING",
#             progress_percentage=65,
#         )
#         self.repository.update_stage(
#             run_id=run_id,
#             stage_name="DEPENDENCY_MAPPING",
#             stage_status="RUNNING",
#             message="Mapping database dependencies",
#         )

#         try:
#             dependencies = self.dependency_agent.run(
#                 state.get("objects", [])
#             )
#             saved_dependencies = self.repository.save_dependencies(
#                 run_id=run_id,
#                 edges=dependencies,
#                 objects=state.get("objects", []),
#             )
#             self.repository.update_stage(
#                 run_id=run_id,
#                 stage_name="DEPENDENCY_MAPPING",
#                 stage_status="COMPLETED",
#                 message=f"Mapped {len(dependencies)} dependencies",
#                 processed_items=len(dependencies),
#                 total_items=len(dependencies),
#             )
#             self.repository.update_run_status(
#                 run_id=run_id,
#                 status="RUNNING",
#                 current_stage="DEPENDENCY_MAPPING",
#                 progress_percentage=75,
#             )
#             return {
#                 **state,
#                 "dependencies": dependencies,
#                 "dependency_records": saved_dependencies,
#             }
#         except Exception as error:
#             safe_error = (
#                 "Dependency mapping failed: "
#                 f"{error.__class__.__name__}"
#             )
#             self.repository.update_stage(
#                 run_id=run_id,
#                 stage_name="DEPENDENCY_MAPPING",
#                 stage_status="FAILED",
#                 message="Dependency mapping failed",
#                 error_code="DEPENDENCY_MAPPING_FAILED",
#                 error_message=safe_error,
#             )
#             self.repository.update_run_status(
#                 run_id=run_id,
#                 status="FAILED",
#                 current_stage="DEPENDENCY_MAPPING",
#                 progress_percentage=65,
#                 error_code="DEPENDENCY_MAPPING_FAILED",
#                 error_message=safe_error,
#             )
#             raise

#     def _compliance(self, state: DiscoveryState) -> DiscoveryState:
#         run_id = state["discovery_run_id"]
#         selected = set(state.get("selected_frameworks", []))
#         generic_requested = (
#             "REGULATORY_COMPLIANCE" in state["effective_scopes"]
#         )
#         legacy_hipaa = (
#             "HIPAA_COMPLIANCE" in state["effective_scopes"]
#         )
#         if not generic_requested and not legacy_hipaa:
#             return state
#         stage_name = (
#             "REGULATORY_COMPLIANCE"
#             if generic_requested
#             else "HIPAA_COMPLIANCE"
#         )
#         self.repository.update_run_status(
#             run_id, "RUNNING", stage_name, 78
#         )
#         self.repository.update_stage(
#             run_id, stage_name, "RUNNING",
#             "Evaluating selected compliance policy packs",
#         )
#         try:
#             classification_records = state.get(
#                 "classification_records", []
#             )
#             assessments: dict[str, Any] = {}
#             legacy_output: dict[str, Any] = {}

#             if "HIPAA" in selected:
#                 findings, score = self.hipaa_agent.evaluate(
#                     state.get("classifications", [])
#                 )
#                 saved_findings = self.repository.save_hipaa_findings(
#                     run_id, findings, classification_records
#                 )
#                 score_id = self.repository.save_hipaa_score(
#                     run_id, score
#                 )
#                 generic_hipaa = (
#                     self.repository.save_generic_hipaa_result(
#                         run_id, saved_findings, score
#                     )
#                 )
#                 assessments["HIPAA"] = (
#                     self.repository.save_control_assessment(
#                         run_id=run_id,
#                         framework_code="HIPAA",
#                         classification_records=classification_records,
#                         evaluator=evaluate_hipaa_controls,
#                     )
#                 )
#                 legacy_output = {
#                     "hipaa_findings": findings,
#                     "hipaa_finding_records": saved_findings,
#                     "hipaa_score": score,
#                     "hipaa_score_id": score_id,
#                     "generic_hipaa_result": generic_hipaa,
#                 }

#             if "PCI_DSS" in selected:
#                 assessments["PCI_DSS"] = (
#                     self.repository.save_control_assessment(
#                         run_id=run_id,
#                         framework_code="PCI_DSS",
#                         classification_records=classification_records,
#                         evaluator=evaluate_pci_dss_controls,
#                         finding_builder=(
#                             build_pci_dss_classification_findings
#                         ),
#                     )
#                 )

#             self.repository.update_stage(
#                 run_id, stage_name, "COMPLETED",
#                 f"Evaluated {len(assessments)} policy pack(s)",
#                 len(assessments), len(selected),
#             )
#             self.repository.update_run_status(
#                 run_id, "RUNNING", stage_name, 90
#             )
#             return {
#                 **state,
#                 **legacy_output,
#                 "compliance_assessments": assessments,
#             }
#         except Exception as error:
#             safe_error = (
#                 "Compliance evaluation failed: "
#                 f"{error.__class__.__name__}"
#             )
#             self.repository.update_stage(
#                 run_id, stage_name, "FAILED",
#                 "Compliance evaluation failed",
#                 error_code="COMPLIANCE_EVALUATION_FAILED",
#                 error_message=safe_error,
#             )
#             self.repository.update_run_status(
#                 run_id, "FAILED", stage_name, 78,
#                 "COMPLIANCE_EVALUATION_FAILED", safe_error,
#             )
#             raise

#     def _report(self, state: DiscoveryState) -> DiscoveryState:
#         run_id = state["discovery_run_id"]
#         self.repository.update_run_status(
#             run_id=run_id,
#             status="RUNNING",
#             current_stage="REPORT_FINALIZATION",
#             progress_percentage=95,
#         )
#         self.repository.update_stage(
#             run_id=run_id,
#             stage_name="REPORT_FINALIZATION",
#             stage_status="RUNNING",
#             message="Building discovery report",
#         )

#         report = self.report_agent.build(state)

#         self.repository.update_stage(
#             run_id=run_id,
#             stage_name="REPORT_FINALIZATION",
#             stage_status="COMPLETED",
#             message="Discovery report completed",
#             processed_items=1,
#             total_items=1,
#         )
#         self.repository.update_run_status(
#             run_id=run_id,
#             status="SUCCEEDED",
#             current_stage="REPORT_FINALIZATION",
#             progress_percentage=100,
#         )
#         return {**state, "report": report, "status": "SUCCEEDED"}

#     def _build_graph(self):
#         graph = StateGraph(DiscoveryState)
#         graph.add_node("metadata_and_profiling", self._metadata)
#         graph.add_node("classification", self._classify)
#         graph.add_node("dependency_mapping", self._dependencies)
#         graph.add_node("compliance", self._compliance)
#         graph.add_node("report", self._report)

#         graph.add_edge(START, "metadata_and_profiling")
#         graph.add_edge("metadata_and_profiling", "classification")
#         graph.add_edge("classification", "dependency_mapping")
#         graph.add_edge("dependency_mapping", "compliance")
#         graph.add_edge("compliance", "report")
#         graph.add_edge("report", END)
#         return graph.compile()

#     def invoke(
#         self,
#         discovery_run_id: str,
#         connection_id: int,
#         scopes: list[str],
#         source_connection: Any,
#         selected_objects: list[dict[str, str]] | None = None,
#         selected_frameworks: list[str] | None = None,
#     ) -> DiscoveryState:
#         effective_scopes = set(scopes)
#         if (
#             "HIPAA_COMPLIANCE" in effective_scopes
#             or "REGULATORY_COMPLIANCE" in effective_scopes
#         ):
#             effective_scopes.add("COLUMN_CLASSIFICATION")
#         framework_codes = list(selected_frameworks or [])
#         if (
#             "HIPAA_COMPLIANCE" in effective_scopes
#             and "HIPAA" not in framework_codes
#         ):
#             framework_codes.append("HIPAA")

#         initial_state: DiscoveryState = {
#             "discovery_run_id": discovery_run_id,
#             "connection_id": connection_id,
#             "requested_scopes": scopes,
#             "effective_scopes": sorted(effective_scopes),
#             "selected_objects": selected_objects or [],
#             "selected_frameworks": framework_codes,
#             "source_connection": source_connection,
#             "errors": [],
#             "status": "PENDING",
#         }
#         return self.graph.invoke(initial_state)
from __future__ import annotations

import asyncio
from typing import Any
from types import SimpleNamespace
from langgraph.graph import END, START, StateGraph

from src.orchestration.state import DiscoveryState
from src.repositories.compliance_repository import ComplianceRepository
from src.repositories.discovery_repository import DiscoveryRepository
from src.services.compliance_service import ComplianceService
from src.tools.classification_policy import (
    build_classification_summary,
    reconcile_linked_identifiers,
)


class DiscoverySupervisor:
    def __init__(
        self,
        metadata_agent,
        classification_agent,
        dependency_agent,
        compliance_service: ComplianceService,
        compliance_repository: ComplianceRepository,
        report_agent,
        repository: DiscoveryRepository,
    ):
        self.metadata_agent = metadata_agent
        self.classification_agent = classification_agent
        self.dependency_agent = dependency_agent
        self.compliance_service = compliance_service
        self.compliance_repository = compliance_repository
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
            self.repository.update_stage(
                run_id, "COLUMN_CLASSIFICATION", "COMPLETED", message, len(results), summary["eligible_columns"]
            )
            self.repository.update_run_status(run_id, "RUNNING", "COLUMN_CLASSIFICATION", 60)
            return {
                **state,
                "classifications": results,
                "classification_records": saved,
                "classification_summary": summary,
            }
        except Exception as error:
            safe = f"Column classification failed: {error.__class__.__name__}"
            self.repository.update_stage(
                run_id, "COLUMN_CLASSIFICATION", "FAILED", "Column classification failed",
                error_code="CLASSIFICATION_FAILED", error_message=safe
            )
            self.repository.update_run_status(
                run_id, "FAILED", "COLUMN_CLASSIFICATION", 40, "CLASSIFICATION_FAILED", safe
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
            dependencies = self.dependency_agent.run(state.get("objects", []))
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
            safe_error = f"Dependency mapping failed: {error.__class__.__name__}"
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

    # def _compliance(self, state: DiscoveryState) -> DiscoveryState:
    #     run_id = state["discovery_run_id"]
    #     selected_frameworks = list(state.get("selected_frameworks", []))

    #     # Check if regulatory compliance was requested or frameworks were selected
    #     if "REGULATORY_COMPLIANCE" not in state["effective_scopes"] and not selected_frameworks:
    #         return state

    #     stage_name = "REGULATORY_COMPLIANCE"
    #     self.repository.update_run_status(run_id, "RUNNING", stage_name, 78)
    #     self.repository.update_stage(
    #         run_id, stage_name, "RUNNING",
    #         f"Evaluating compliance across frameworks: {', '.join(selected_frameworks)}",
    #     )

    #     try:
    #         classification_records = state.get("classification_records", [])

    #         # Group classified columns by table
    #         columns_by_table: dict[str, list[dict[str, Any]]] = {}
    #         for col in classification_records:
    #             table = col.get("table_name", "default_table")
    #             columns_by_table.setdefault(table, []).append(col)

    #         all_results = []

    #         # Run Stage 4 audit for each table across selected frameworks
    #         for table_name, cols in columns_by_table.items():
    #             audit_results = asyncio.run(
    #                 self.compliance_service.evaluate_run_compliance(
    #                     discovery_run_id=str(run_id),
    #                     table_name=table_name,
    #                     classified_columns=cols,
    #                     selected_frameworks=selected_frameworks,
    #                 )
    #             )

    #             # Persist each framework result into the 2 tables
    #             for res in audit_results:
    #                 self.compliance_repository.save_framework_assessment(
    #                     discovery_run_id=str(run_id),
    #                     table_name=table_name,
    #                     framework_result=res,
    #                 )
    #                 all_results.append(res)

    #         message = f"Evaluated {len(all_results)} framework assessment(s) across {len(columns_by_table)} table(s)"
    #         self.repository.update_stage(
    #             run_id, stage_name, "COMPLETED",
    #             message, len(all_results), len(selected_frameworks)
    #         )
    #         self.repository.update_run_status(run_id, "RUNNING", stage_name, 90)

    #         return {
    #             **state,
    #             "compliance_results": all_results,
    #         }

    #     except Exception as error:
    #         safe_error = f"Compliance evaluation failed: {error.__class__.__name__}"
    #         self.repository.update_stage(
    #             run_id, stage_name, "FAILED",
    #             "Compliance evaluation failed",
    #             error_code="COMPLIANCE_EVALUATION_FAILED",
    #             error_message=safe_error,
    #         )
    #         self.repository.update_run_status(
    #             run_id, "FAILED", stage_name, 78,
    #             "COMPLIANCE_EVALUATION_FAILED", safe_error,
    #         )
    #         raise
    # def _compliance(self, state: DiscoveryState) -> DiscoveryState:
    #     run_id = state["discovery_run_id"]
    #     selected_frameworks = list(state.get("selected_frameworks", []))

    #     if "REGULATORY_COMPLIANCE" not in state["effective_scopes"] and not selected_frameworks:
    #         return state

    #     stage_name = "REGULATORY_COMPLIANCE"
    #     self.repository.update_run_status(run_id, "RUNNING", stage_name, 78)
    #     self.repository.update_stage(
    #         run_id, stage_name, "RUNNING",
    #         f"Evaluating compliance across frameworks: {', '.join(selected_frameworks)}",
    #     )

    #     try:
    #         from src.services.compliance_service import calculate_metrics

    #         classification_records = state.get("classification_records", [])

    #         # Group classified columns by table
    #         columns_by_table: dict[str, list[dict[str, Any]]] = {}
    #         for col in classification_records:
    #             table = col.get("table_name", "default_table")
    #             columns_by_table.setdefault(table, []).append(col)

    #         # Dictionary to collect findings across all tables per framework
    #         findings_by_framework: dict[str, list[Any]] = {
    #             fw.upper().strip(): [] for fw in selected_frameworks
    #         }

    #         # 1. Run audit per table across selected frameworks
    #         for table_name, cols in columns_by_table.items():
    #             audit_results = asyncio.run(
    #                 self.compliance_service.evaluate_run_compliance(
    #                     discovery_run_id=str(run_id),
    #                     table_name=table_name,
    #                     classified_columns=cols,
    #                     selected_frameworks=selected_frameworks,
    #                 )
    #             )

    #             for res in audit_results:
    #                 fw_code = res.framework_code.upper().strip()
    #                 for f in res.findings:
    #                     # Attach table_name so findings know which table they belong to
    #                     setattr(f, "table_name", table_name)
    #                     findings_by_framework.setdefault(fw_code, []).append(f)

    #         # 2. Compute run-level score & persist once per framework
    #         persisted_frameworks = []
    #         for fw_code, all_findings in findings_by_framework.items():
    #             metrics = calculate_metrics(all_findings)
    #             self.compliance_repository.save_framework_assessment(
    #                 discovery_run_id=str(run_id),
    #                 framework_code=fw_code,
    #                 metrics=metrics,
    #                 findings=all_findings,
    #             )
    #             persisted_frameworks.append({
    #                 "framework_code": fw_code,
    #                 "score": metrics.score,
    #                 "risk_band": metrics.risk_band,
    #                 "findings_count": len(all_findings),
    #             })

    #         message = f"Evaluated {len(persisted_frameworks)} framework(s) across {len(columns_by_table)} table(s)"
    #         self.repository.update_stage(
    #             run_id, stage_name, "COMPLETED",
    #             message, len(persisted_frameworks), len(selected_frameworks)
    #         )
    #         self.repository.update_run_status(run_id, "RUNNING", stage_name, 90)

    #         return {
    #             **state,
    #             "compliance_results": persisted_frameworks,
    #         }

    #     except Exception as error:
    #         safe_error = f"Compliance evaluation failed: {error.__class__.__name__}"
    #         self.repository.update_stage(
    #             run_id, stage_name, "FAILED",
    #             "Compliance evaluation failed",
    #             error_code="COMPLIANCE_EVALUATION_FAILED",
    #             error_message=safe_error,
    #         )
    #         self.repository.update_run_status(
    #             run_id, "FAILED", stage_name, 78,
    #             "COMPLIANCE_EVALUATION_FAILED", safe_error,
    #         )
    #         raise
    # def _compliance(self, state: DiscoveryState) -> DiscoveryState:
    #     run_id = state["discovery_run_id"]
    #     selected_frameworks = list(state.get("selected_frameworks", []))

    #     if "REGULATORY_COMPLIANCE" not in state["effective_scopes"] and not selected_frameworks:
    #         return state

    #     stage_name = "REGULATORY_COMPLIANCE"
    #     self.repository.update_run_status(run_id, "RUNNING", stage_name, 78)
    #     self.repository.update_stage(
    #         run_id, stage_name, "RUNNING",
    #         f"Evaluating compliance across frameworks: {', '.join(selected_frameworks)}",
    #     )

    #     try:
    #         from src.services.compliance_service import calculate_metrics

    #         classification_records = state.get("classification_records", [])

    #         # Group classified columns by table
    #         columns_by_table: dict[str, list[dict[str, Any]]] = {}
    #         for col in classification_records:
    #             table = col.get("table_name", "default_table")
    #             columns_by_table.setdefault(table, []).append(col)

    #         # Dictionary to collect findings across all tables per framework
    #         findings_by_framework: dict[str, list[Any]] = {
    #             fw.upper().strip(): [] for fw in selected_frameworks
    #         }

    #         # 1. Evaluate each table and accumulate findings
    #         for table_name, cols in columns_by_table.items():
    #             audit_results = asyncio.run(
    #                 self.compliance_service.evaluate_run_compliance(
    #                     discovery_run_id=str(run_id),
    #                     table_name=table_name,
    #                     classified_columns=cols,
    #                     selected_frameworks=selected_frameworks,
    #                 )
    #             )

    #             for res in audit_results:
    #                 fw_code = res.framework_code.upper().strip()
    #                 for f in res.findings:
    #                     setattr(f, "table_name", table_name)
    #                     findings_by_framework.setdefault(fw_code, []).append(f)

    #         # 2. Persist one consolidated assessment per framework
    #         persisted_frameworks = []
    #         for fw_code, all_findings in findings_by_framework.items():
    #             metrics = calculate_metrics(all_findings)
    #             self.compliance_repository.save_framework_assessment(
    #                 discovery_run_id=str(run_id),
    #                 framework_code=fw_code,
    #                 metrics=metrics,
    #                 findings=all_findings,
    #             )
    #             persisted_frameworks.append({
    #                 "framework_code": fw_code,
    #                 "score": metrics.score,
    #                 "risk_band": str(metrics.risk_band),
    #                 "findings_count": len(all_findings),
    #             })

    #         message = f"Evaluated {len(persisted_frameworks)} framework(s) across {len(columns_by_table)} table(s)"
    #         self.repository.update_stage(
    #             run_id, stage_name, "COMPLETED",
    #             message, len(persisted_frameworks), len(selected_frameworks)
    #         )
    #         self.repository.update_run_status(run_id, "RUNNING", stage_name, 90)

    #         return {
    #             **state,
    #             "compliance_results": persisted_frameworks,
    #         }

    #     except Exception as error:
    #         safe_error = f"Compliance evaluation failed: {error.__class__.__name__}"
    #         self.repository.update_stage(
    #             run_id, stage_name, "FAILED",
    #             "Compliance evaluation failed",
    #             error_code="COMPLIANCE_EVALUATION_FAILED",
    #             error_message=safe_error,
    #         )
    #         self.repository.update_run_status(
    #             run_id, "FAILED", stage_name, 78,
    #             "COMPLIANCE_EVALUATION_FAILED", safe_error,
    #         )
    #         raise
    def _compliance(self, state: DiscoveryState) -> DiscoveryState:
        run_id = state["discovery_run_id"]
        selected_frameworks = list(state.get("selected_frameworks", []))

        if "REGULATORY_COMPLIANCE" not in state["effective_scopes"] and not selected_frameworks:
            return state

        stage_name = "REGULATORY_COMPLIANCE"
        self.repository.update_run_status(run_id, "RUNNING", stage_name, 78)
        self.repository.update_stage(
            run_id, stage_name, "RUNNING",
            f"Evaluating compliance across frameworks: {', '.join(selected_frameworks)}",
        )

        try:
            from src.services.compliance_service import calculate_metrics

            classification_records = state.get("classification_records", [])

            # Group classified columns by table
            columns_by_table: dict[str, list[dict[str, Any]]] = {}
            for col in classification_records:
                table = col.get("table_name", "default_table")
                columns_by_table.setdefault(table, []).append(col)

            # Dictionary to collect findings across all tables per framework
            findings_by_framework: dict[str, list[Any]] = {
                fw.upper().strip(): [] for fw in selected_frameworks
            }

            # 1. Evaluate each table and accumulate findings
            for table_name, cols in columns_by_table.items():
                audit_results = asyncio.run(
                    self.compliance_service.evaluate_run_compliance(
                        discovery_run_id=str(run_id),
                        table_name=table_name,
                        classified_columns=cols,
                        selected_frameworks=selected_frameworks,
                    )
                )

                for res in audit_results:
                    fw_code = res.framework_code.upper().strip()
                    for f in res.findings:
                        # Convert to dict and wrap in SimpleNamespace to safely attach table_name
                        f_data = f.model_dump() if hasattr(f, "model_dump") else dict(f)
                        f_data["table_name"] = table_name
                        wrapped_finding = SimpleNamespace(**f_data)
                        findings_by_framework.setdefault(fw_code, []).append(wrapped_finding)

            # 2. Persist one consolidated assessment per framework
            persisted_frameworks = []
            for fw_code, all_findings in findings_by_framework.items():
                metrics = calculate_metrics(all_findings)
                self.compliance_repository.save_framework_assessment(
                    discovery_run_id=str(run_id),
                    framework_code=fw_code,
                    metrics=metrics,
                    findings=all_findings,
                )
                persisted_frameworks.append({
                    "framework_code": fw_code,
                    "score": metrics.score,
                    "risk_band": str(getattr(metrics.risk_band, "value", metrics.risk_band)),
                    "findings_count": len(all_findings),
                    "findings": [vars(f) for f in all_findings],
                })

            message = f"Evaluated {len(persisted_frameworks)} framework(s) across {len(columns_by_table)} table(s)"
            self.repository.update_stage(
                run_id, stage_name, "COMPLETED",
                message, len(persisted_frameworks), len(selected_frameworks)
            )
            self.repository.update_run_status(run_id, "RUNNING", stage_name, 90)

            return {
                **state,
                "compliance_results": persisted_frameworks,
            }

        except Exception as error:
            safe_error = f"Compliance evaluation failed: {error.__class__.__name__}"
            self.repository.update_stage(
                run_id, stage_name, "FAILED",
                "Compliance evaluation failed",
                error_code="COMPLIANCE_EVALUATION_FAILED",
                error_message=safe_error,
            )
            self.repository.update_run_status(
                run_id, "FAILED", stage_name, 78,
                "COMPLIANCE_EVALUATION_FAILED", safe_error,
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
        graph.add_node("compliance", self._compliance)
        graph.add_node("report", self._report)

        graph.add_edge(START, "metadata_and_profiling")
        graph.add_edge("metadata_and_profiling", "classification")
        graph.add_edge("classification", "dependency_mapping")
        graph.add_edge("dependency_mapping", "compliance")
        graph.add_edge("compliance", "report")
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
        framework_codes = list(selected_frameworks or [])

        # Auto-enable Stage 3 & Stage 5 when frameworks are selected
        if framework_codes or "REGULATORY_COMPLIANCE" in effective_scopes:
            effective_scopes.add("COLUMN_CLASSIFICATION")
            effective_scopes.add("REGULATORY_COMPLIANCE")

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