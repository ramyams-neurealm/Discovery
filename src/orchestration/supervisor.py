from __future__ import annotations

import logging
from typing import Any

from langgraph.graph import END, START, StateGraph

from src.agents.ccpa_compliance_score_agent import (
    CcpaComplianceScoreAgent,
)
from src.agents.dpdp_compliance_score_agent import (
    DpdpComplianceScoreAgent,
)
from src.agents.gdpr_compliance_score_agent import (
    GdprComplianceScoreAgent,
)
from src.agents.glba_compliance_score_agent import (
    GlbaComplianceScoreAgent,
)
from src.agents.hipaa_compliance_score_agent import (
    HipaaComplianceScoreAgent,
)
from src.agents.pci_dss_compliance_score_agent import (
    PciDssComplianceScoreAgent,
)
from src.agents.pipeda_compliance_score_agent import (
    PipedaComplianceScoreAgent,
)
from src.orchestration.state import DiscoveryState
from src.repositories.discovery_repository import (
    DiscoveryRepository,
)
from src.services.key_vault_service import KeyVaultService
from src.tools.classification_policy import (
    build_classification_summary,
    reconcile_linked_identifiers,
)
from src.tools.glba_control_policy import (
    build_glba_classification_findings,
    evaluate_glba_controls,
)
from src.tools.hipaa_control_policy import (
    evaluate_hipaa_controls,
)
from src.tools.dpdp_control_policy import (
    evaluate_dpdp_controls,
)
from src.tools.pci_dss_control_policy import (
    build_pci_dss_classification_findings,
    evaluate_pci_dss_controls,
)
from src.tools.ccpa_control_policy import (
    evaluate_ccpa_controls,
)
from src.tools.pipeda_control_policy import (
    evaluate_pipeda_controls,
)
from src.tools.gdpr_control_policy import (
    evaluate_gdpr_controls,
)

from src.tools.profiling_tools import is_table_object
from src.utils.config import Settings


logger = logging.getLogger(__name__)


class DiscoverySupervisor:
    def __init__(
        self,
        metadata_agent,
        classification_agent,
        dependency_agent,
        hipaa_agent: HipaaComplianceScoreAgent,
        report_agent,
        repository: DiscoveryRepository,
        settings: Settings,
        key_vault: KeyVaultService,
    ):
        self.metadata_agent = metadata_agent
        self.classification_agent = classification_agent
        self.dependency_agent = dependency_agent
        self.hipaa_agent = hipaa_agent
        self.report_agent = report_agent
        self.repository = repository
        self.settings = settings
        self.key_vault = key_vault
        self.graph = self._build_graph()

    def _metadata(self, state: DiscoveryState):
        run_id = state["discovery_run_id"]

        try:
            selected_objects = list(
                state.get("selected_objects") or []
            )

            output = self.metadata_agent.run(
                run_id=run_id,
                connection_id=state["connection_id"],
                source_connection=state[
                    "source_connection"
                ],
                selected_objects=selected_objects,
            )

            safe_output = (
                output
                if isinstance(output, dict)
                else {}
            )

            metadata_state = {
                "metadata_profile": (
                    safe_output.get("profile_data")
                    or {}
                ),
                "objects": (
                    safe_output.get("objects")
                    or []
                ),
                "table_profiles": (
                    safe_output.get("table_profiles")
                    or []
                ),
                "column_profiles": (
                    safe_output.get("column_profiles")
                    or []
                ),
                "profile_errors": (
                    safe_output.get("profile_errors")
                    or []
                ),
                "metadata_error": (
                    safe_output.get("metadata_error")
                ),
            }

            if metadata_state["metadata_error"]:
                raise RuntimeError(
                    metadata_state["metadata_error"]
                )

            if selected_objects:
                expected_count = len(
                    selected_objects
                )

                actual_count = len(
                    metadata_state["objects"]
                )

                if actual_count > expected_count:
                    raise RuntimeError(
                        "Metadata discovery returned more "
                        "objects than were selected. "
                        f"Selected: {expected_count}; "
                        f"returned: {actual_count}."
                    )

            has_table_objects = any(
                is_table_object(item)
                for item in metadata_state["objects"]
            )

            if (
                has_table_objects
                and not metadata_state[
                    "column_profiles"
                ]
            ):
                raise RuntimeError(
                    "Metadata discovery returned table "
                    "objects but no column profiles."
                )

            errors = list(
                state.get("errors") or []
            )

            for profile_error in metadata_state[
                "profile_errors"
            ]:
                errors.append(
                    {
                        "stage": (
                            "METADATA_PROFILING"
                        ),
                        "error": profile_error,
                    }
                )

            self.repository.update_run_status(
                run_id=run_id,
                status="RUNNING",
                current_stage=(
                    "METADATA_PROFILING"
                ),
                progress_percentage=35,
                error_code=None,
                error_message=None,
            )

            return {
                **state,
                **metadata_state,
                "errors": errors,
                "status": "RUNNING",
            }

        except Exception as error:
            safe_error = (
                "Metadata profiling failed: "
                f"{error}"
            )

            logger.error(
                safe_error,
                exc_info=True,
                extra={
                    "discovery_run_id": run_id,
                },
            )

            try:
                self.repository.update_stage(
                    run_id=run_id,
                    stage_name=(
                        "METADATA_PROFILING"
                    ),
                    stage_status="FAILED",
                    message=(
                        "Metadata profiling failed"
                    ),
                    processed_items=0,
                    total_items=0,
                    error_code=(
                        "METADATA_DISCOVERY_FAILED"
                    ),
                    error_message=safe_error,
                )

                self.repository.update_run_status(
                    run_id=run_id,
                    status="FAILED",
                    current_stage=(
                        "METADATA_PROFILING"
                    ),
                    progress_percentage=10,
                    error_code=(
                        "METADATA_DISCOVERY_FAILED"
                    ),
                    error_message=safe_error,
                )

            except Exception:
                logger.error(
                    "Could not persist metadata failure",
                    exc_info=True,
                    extra={
                        "discovery_run_id": run_id,
                    },
                )

            raise

    def _classify(self, state: DiscoveryState):
        run_id = state["discovery_run_id"]

        effective_scopes = set(
            state.get("effective_scopes") or []
        )

        if (
            "COLUMN_CLASSIFICATION"
            not in effective_scopes
        ):
            return state

        profiles = list(
            state.get("column_profiles") or []
        )

        self.repository.update_run_status(
            run_id=run_id,
            status="RUNNING",
            current_stage=(
                "COLUMN_CLASSIFICATION"
            ),
            progress_percentage=40,
            error_code=None,
            error_message=None,
        )

        self.repository.update_stage(
            run_id=run_id,
            stage_name=(
                "COLUMN_CLASSIFICATION"
            ),
            stage_status="RUNNING",
            message=(
                "Classifying discovered columns"
            ),
            processed_items=0,
            total_items=len(profiles),
            error_code=None,
            error_message=None,
        )

        try:
            payload_keys = (
                "object_id",
                "column_id",
                "schema_name",
                "table_name",
                "column_name",
                "data_type",
                "nullable",
                "is_primary_key",
                "is_foreign_key",
                "neighboring_columns",
                "masked_samples",
                "null_percentage",
                "distinct_count",
            )

            column_payloads = [
                {
                    key: profile.get(key)
                    for key in payload_keys
                }
                for profile in profiles
            ]

            max_concurrency = int(
                getattr(
                    self.settings,
                    "classification_max_concurrency",
                    5,
                )
            )

            max_concurrency = max(
                1,
                min(max_concurrency, 10),
            )

            results = (
                self.classification_agent
                .classify_batch(
                    column_payloads=column_payloads,
                    max_concurrency=(
                        max_concurrency
                    ),
                )
            )

            results = reconcile_linked_identifiers(
                results,
                state.get("objects") or [],
            )

            summary = build_classification_summary(
                state.get("objects") or [],
                profiles,
                results,
            )

            column_ids = {
                (
                    profile["schema_name"],
                    profile["table_name"],
                    profile["column_name"],
                ): profile["column_id"]
                for profile in profiles
            }

            saved_records = (
                self.repository
                .save_classifications(
                    run_id,
                    results,
                    column_ids,
                )
            )

            classified_columns = int(
                summary.get(
                    "classified_columns",
                    len(results),
                )
            )

            discovered_columns = int(
                summary.get(
                    "discovered_columns",
                    len(profiles),
                )
            )

            eligible_columns = int(
                summary.get(
                    "eligible_columns",
                    len(profiles),
                )
            )

            excluded_columns = int(
                summary.get(
                    "excluded_columns",
                    0,
                )
            )

            message = (
                f"Classified {classified_columns} "
                f"of {discovered_columns} "
                "discovered columns; "
                f"{excluded_columns} excluded "
                "because they had no eligible "
                "table profile."
            )

            self.repository.update_stage(
                run_id=run_id,
                stage_name=(
                    "COLUMN_CLASSIFICATION"
                ),
                stage_status="COMPLETED",
                message=message,
                processed_items=len(results),
                total_items=eligible_columns,
                error_code=None,
                error_message=None,
            )

            self.repository.update_run_status(
                run_id=run_id,
                status="RUNNING",
                current_stage=(
                    "COLUMN_CLASSIFICATION"
                ),
                progress_percentage=60,
                error_code=None,
                error_message=None,
            )

            return {
                **state,
                "classifications": results,
                "classification_records": (
                    saved_records
                ),
                "classification_summary": summary,
            }

        except Exception as error:
            safe_error = (
                "Column classification failed: "
                f"{error.__class__.__name__}"
            )

            self.repository.update_stage(
                run_id=run_id,
                stage_name=(
                    "COLUMN_CLASSIFICATION"
                ),
                stage_status="FAILED",
                message=(
                    "Column classification failed"
                ),
                error_code=(
                    "CLASSIFICATION_FAILED"
                ),
                error_message=safe_error,
            )

            self.repository.update_run_status(
                run_id=run_id,
                status="FAILED",
                current_stage=(
                    "COLUMN_CLASSIFICATION"
                ),
                progress_percentage=40,
                error_code=(
                    "CLASSIFICATION_FAILED"
                ),
                error_message=safe_error,
            )

            raise

    def _dependencies(self, state: DiscoveryState):
        run_id = state["discovery_run_id"]

        effective_scopes = set(
            state.get("effective_scopes") or []
        )

        dependency_requested = (
            "DEPENDENCY_MAPPING" in effective_scopes
            or "DEPENDENCY_MAP" in effective_scopes
        )

        if not dependency_requested:
            return state

        objects = list(
            state.get("objects") or []
        )

        self.repository.update_run_status(
            run_id=run_id,
            status="RUNNING",
            current_stage="DEPENDENCY_MAPPING",
            progress_percentage=65,
            error_code=None,
            error_message=None,
        )

        self.repository.update_stage(
            run_id=run_id,
            stage_name="DEPENDENCY_MAPPING",
            stage_status="RUNNING",
            message="Mapping database dependencies",
            processed_items=0,
            total_items=0,
            error_code=None,
            error_message=None,
        )

        try:
            generated_dependencies = (
                self.dependency_agent.run(objects)
                or []
            )

            saved_dependencies = (
                self.repository.save_dependencies(
                    run_id=run_id,
                    edges=generated_dependencies,
                    objects=objects,
                )
                or []
            )

            generated_count = len(
                generated_dependencies
            )

            saved_count = len(
                saved_dependencies
            )

            skipped_count = max(
                generated_count - saved_count,
                0,
            )

            if skipped_count:
                message = (
                    f"Identified {generated_count} "
                    "dependency relationship(s); "
                    f"saved {saved_count} relationship(s) "
                    "within the selected discovery scope; "
                    f"skipped {skipped_count} relationship(s) "
                    "because the source or target object "
                    "was outside the selected scope."
                )
            else:
                message = (
                    f"Mapped and saved {saved_count} "
                    "dependency relationship(s)."
                )

            self.repository.update_stage(
                run_id=run_id,
                stage_name="DEPENDENCY_MAPPING",
                stage_status="COMPLETED",
                message=message,
                processed_items=saved_count,
                total_items=generated_count,
                error_code=None,
                error_message=None,
            )

            self.repository.update_run_status(
                run_id=run_id,
                status="RUNNING",
                current_stage="DEPENDENCY_MAPPING",
                progress_percentage=75,
                error_code=None,
                error_message=None,
            )

            logger.info(
                "Dependency mapping completed",
                extra={
                    "discovery_run_id": run_id,
                    "selected_object_count": len(
                        objects
                    ),
                    "generated_dependency_count": (
                        generated_count
                    ),
                    "saved_dependency_count": (
                        saved_count
                    ),
                    "skipped_dependency_count": (
                        skipped_count
                    ),
                },
            )

            return {
                **state,
                "dependencies": saved_dependencies,
                "dependency_records": (
                    saved_dependencies
                ),
                "generated_dependencies": (
                    generated_dependencies
                ),
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
                processed_items=0,
                total_items=0,
                error_code=(
                    "DEPENDENCY_MAPPING_FAILED"
                ),
                error_message=safe_error,
            )

            self.repository.update_run_status(
                run_id=run_id,
                status="FAILED",
                current_stage="DEPENDENCY_MAPPING",
                progress_percentage=65,
                error_code=(
                    "DEPENDENCY_MAPPING_FAILED"
                ),
                error_message=safe_error,
            )

            raise

    def _compliance(self, state: DiscoveryState):
        run_id = state["discovery_run_id"]

        effective_scopes = set(
            state.get("effective_scopes") or []
        )

        generic_requested = (
            "REGULATORY_COMPLIANCE"
            in effective_scopes
        )

        legacy_hipaa_requested = (
            "HIPAA_COMPLIANCE"
            in effective_scopes
        )

        if (
            not generic_requested
            and not legacy_hipaa_requested
        ):
            return state

        selected_frameworks = {
            str(framework).strip().upper()
            for framework in (
                state.get("selected_frameworks")
                or []
            )
            if str(framework).strip()
        }

        if legacy_hipaa_requested:
            selected_frameworks.add("HIPAA")

        if not selected_frameworks:
            raise ValueError(
                "Regulatory compliance was requested "
                "without any selected frameworks."
            )

        supported_frameworks = {
            "HIPAA",
            "GDPR",
            "PCI_DSS",
            "GLBA",
            "DPDP",
            "CCPA_CPRA",
            "CCPA",
            "PIPEDA",
        }

        unsupported_frameworks = (
            selected_frameworks
            - supported_frameworks
        )

        if unsupported_frameworks:
            raise ValueError(
                "Unsupported compliance framework(s): "
                + ", ".join(
                    sorted(unsupported_frameworks)
                )
            )

        stage_name = (
            "REGULATORY_COMPLIANCE"
            if generic_requested
            else "HIPAA_COMPLIANCE"
        )

        self.repository.update_run_status(
            run_id=run_id,
            status="RUNNING",
            current_stage=stage_name,
            progress_percentage=78,
            error_code=None,
            error_message=None,
        )

        self.repository.update_stage(
            run_id=run_id,
            stage_name=stage_name,
            stage_status="RUNNING",
            message=(
                "Evaluating selected compliance "
                "policy packs"
            ),
            processed_items=0,
            total_items=len(
                selected_frameworks
            ),
            error_code=None,
            error_message=None,
        )

        try:
            classification_records = list(
                state.get(
                    "classification_records"
                )
                or []
            )

            safe_classifications = list(
                state.get("classifications")
                or []
            )

            assessments = {}
            legacy_output = {}
            compliance_findings = []
            compliance_scores = {}
            framework_errors = {}

            if "HIPAA" in selected_frameworks:
                try:
                    findings, score = (
                        self.hipaa_agent.evaluate(
                            safe_classifications
                        )
                    )

                    findings = findings or []

                    saved_findings = (
                        self.repository
                        .save_hipaa_findings(
                            run_id,
                            findings,
                            classification_records,
                        )
                    )

                    score_id = None
                    generic_hipaa = None

                    if score is not None:
                        score_id = (
                            self.repository
                            .save_hipaa_score(
                                run_id,
                                score,
                            )
                        )

                        generic_hipaa = (
                            self.repository
                            .save_generic_hipaa_result(
                                run_id,
                                saved_findings,
                                score,
                            )
                        )

                    assessments["HIPAA"] = (
                        self.repository
                        .save_control_assessment(
                            run_id=run_id,
                            framework_code="HIPAA",
                            classification_records=(
                                classification_records
                            ),
                            evaluator=(
                                evaluate_hipaa_controls
                            ),
                        )
                    )

                    legacy_output.update(
                        {
                            "hipaa_findings": (
                                findings
                            ),
                            "hipaa_finding_records": (
                                saved_findings
                            ),
                            "hipaa_score": score,
                            "hipaa_score_id": score_id,
                            "generic_hipaa_result": (
                                generic_hipaa
                            ),
                        }
                    )

                    compliance_findings.extend(
                        findings
                    )

                    compliance_scores["HIPAA"] = (
                        score
                    )

                except Exception as error:
                    framework_errors["HIPAA"] = (
                        error.__class__.__name__
                    )

                    logger.error(
                        "HIPAA evaluation failed",
                        exc_info=True,
                        extra={
                            "discovery_run_id": (
                                run_id
                            ),
                        },
                    )

            if "GDPR" in selected_frameworks:
                try:
                    agent = GdprComplianceScoreAgent(
                        settings=self.settings,
                        key_vault=self.key_vault,
                    )

                    findings, score = agent.evaluate(
                        safe_classifications
                    )

                    findings = findings or []

                    legacy_output.update(
                        {
                            "gdpr_findings": findings,
                            "gdpr_score": score,
                        }
                    )

                    compliance_findings.extend(
                        findings
                    )

                    assessments["GDPR"] = (
                        self.repository
                        .save_control_assessment(
                            run_id=run_id,
                            framework_code="GDPR",
                            classification_records=(
                                classification_records
                            ),
                            evaluator=(
                                evaluate_gdpr_controls
                            ),
                        )
                    )

                    compliance_scores["GDPR"] = score

                except Exception as error:
                    framework_errors["GDPR"] = (
                        error.__class__.__name__
                    )

                    logger.error(
                        "GDPR evaluation failed",
                        exc_info=True,
                        extra={
                            "discovery_run_id": run_id,
                        },
                    )

            if "PCI_DSS" in selected_frameworks:
                try:
                    agent = (
                        PciDssComplianceScoreAgent(
                            settings=self.settings,
                            key_vault=(
                                self.key_vault
                            ),
                        )
                    )

                    findings, score = agent.evaluate(
                        safe_classifications
                    )

                    findings = findings or []

                    legacy_output.update(
                        {
                            "pci_dss_findings": (
                                findings
                            ),
                            "pci_dss_score": score,
                        }
                    )

                    compliance_findings.extend(
                        findings
                    )

                    compliance_scores[
                        "PCI_DSS"
                    ] = score

                    assessments["PCI_DSS"] = (
                        self.repository
                        .save_control_assessment(
                            run_id=run_id,
                            framework_code=(
                                "PCI_DSS"
                            ),
                            classification_records=(
                                classification_records
                            ),
                            evaluator=(
                                evaluate_pci_dss_controls
                            ),
                            finding_builder=(
                                build_pci_dss_classification_findings
                            ),
                        )
                    )

                except Exception as error:
                    framework_errors["PCI_DSS"] = (
                        error.__class__.__name__
                    )

                    logger.error(
                        "PCI DSS evaluation failed",
                        exc_info=True,
                        extra={
                            "discovery_run_id": (
                                run_id
                            ),
                        },
                    )

            if "GLBA" in selected_frameworks:
                try:
                    agent = GlbaComplianceScoreAgent(
                        settings=self.settings,
                        key_vault=self.key_vault,
                    )

                    findings, score = agent.evaluate(
                        safe_classifications
                    )

                    findings = findings or []

                    legacy_output.update(
                        {
                            "glba_findings": findings,
                            "glba_score": score,
                        }
                    )

                    compliance_findings.extend(
                        findings
                    )

                    compliance_scores["GLBA"] = (
                        score
                    )

                    assessments["GLBA"] = (
                        self.repository
                        .save_control_assessment(
                            run_id=run_id,
                            framework_code="GLBA",
                            classification_records=(
                                classification_records
                            ),
                            evaluator=(
                                evaluate_glba_controls
                            ),
                            finding_builder=(
                                build_glba_classification_findings
                            ),
                        )
                    )

                except Exception as error:
                    framework_errors["GLBA"] = (
                        error.__class__.__name__
                    )

                    logger.error(
                        "GLBA evaluation failed",
                        exc_info=True,
                        extra={
                            "discovery_run_id": (
                                run_id
                            ),
                        },
                    )

            if "DPDP" in selected_frameworks:
                try:
                    agent = DpdpComplianceScoreAgent(
                        settings=self.settings,
                        key_vault=self.key_vault,
                    )

                    findings, score = agent.evaluate(
                        safe_classifications
                    )

                    findings = findings or []

                    legacy_output.update(
                        {
                            "dpdp_findings": findings,
                            "dpdp_score": score,
                        }
                    )

                    compliance_findings.extend(
                        findings
                    )

                    assessments["DPDP"] = (
                        self.repository
                        .save_control_assessment(
                            run_id=run_id,
                            framework_code="DPDP",
                            classification_records=(
                                classification_records
                            ),
                            evaluator=(
                                evaluate_dpdp_controls
                            ),
                        )
                    )

                    compliance_scores["DPDP"] = score

                except Exception as error:
                    framework_errors["DPDP"] = (
                        error.__class__.__name__
                    )

                    logger.error(
                        "DPDP evaluation failed",
                        exc_info=True,
                        extra={
                            "discovery_run_id": run_id,
                        },
                    )

            ccpa_requested = (
                "CCPA_CPRA" in selected_frameworks
                or "CCPA" in selected_frameworks
            )

            if ccpa_requested:
                try:
                    agent = CcpaComplianceScoreAgent(
                        settings=self.settings,
                        key_vault=self.key_vault,
                    )

                    findings, score = agent.evaluate(
                        safe_classifications
                    )

                    findings = findings or []

                    legacy_output.update(
                        {
                            "ccpa_findings": findings,
                            "ccpa_score": score,
                        }
                    )

                    compliance_findings.extend(
                        findings
                    )

                    assessments["CCPA_CPRA"] = (
                        self.repository
                        .save_control_assessment(
                            run_id=run_id,
                            framework_code="CCPA_CPRA",
                            classification_records=(
                                classification_records
                            ),
                            evaluator=(
                                evaluate_ccpa_controls
                            ),
                        )
                    )

                    compliance_scores[
                        "CCPA_CPRA"
                    ] = score

                except Exception as error:
                    framework_errors[
                        "CCPA_CPRA"
                    ] = error.__class__.__name__

                    logger.error(
                        "CCPA/CPRA evaluation failed",
                        exc_info=True,
                        extra={
                            "discovery_run_id": run_id,
                        },
                    )

            if "PIPEDA" in selected_frameworks:
                try:
                    agent = (
                        PipedaComplianceScoreAgent(
                            settings=self.settings,
                            key_vault=self.key_vault,
                        )
                    )

                    findings, score = agent.evaluate(
                        safe_classifications
                    )

                    findings = findings or []

                    legacy_output.update(
                        {
                            "pipeda_findings": findings,
                            "pipeda_score": score,
                        }
                    )

                    compliance_findings.extend(
                        findings
                    )

                    assessments["PIPEDA"] = (
                        self.repository
                        .save_control_assessment(
                            run_id=run_id,
                            framework_code="PIPEDA",
                            classification_records=(
                                classification_records
                            ),
                            evaluator=(
                                evaluate_pipeda_controls
                            ),
                        )
                    )

                    compliance_scores["PIPEDA"] = score

                except Exception as error:
                    framework_errors["PIPEDA"] = (
                        error.__class__.__name__
                    )

                    logger.error(
                        "PIPEDA evaluation failed",
                        exc_info=True,
                        extra={
                            "discovery_run_id": run_id,
                        },
                    )
            normalized_selected = {
                (
                    "CCPA_CPRA"
                    if framework == "CCPA"
                    else framework
                )
                for framework
                in selected_frameworks
            }

            evaluated_frameworks = set(
                compliance_scores.keys()
            )

            missing_frameworks = (
                normalized_selected
                - evaluated_frameworks
            )

            if (
                missing_frameworks
                or framework_errors
            ):
                error_parts = []

                if missing_frameworks:
                    error_parts.append(
                        "Not evaluated: "
                        + ", ".join(
                            sorted(
                                missing_frameworks
                            )
                        )
                    )

                if framework_errors:
                    error_parts.append(
                        "Errors: "
                        + ", ".join(
                            (
                                f"{framework}="
                                f"{error_type}"
                            )
                            for framework, error_type
                            in sorted(
                                framework_errors.items()
                            )
                        )
                    )

                raise RuntimeError(
                    "; ".join(error_parts)
                )

            self.repository.update_stage(
                run_id=run_id,
                stage_name=stage_name,
                stage_status="COMPLETED",
                message=(
                    f"Evaluated "
                    f"{len(evaluated_frameworks)} "
                    "policy pack(s)"
                ),
                processed_items=len(
                    evaluated_frameworks
                ),
                total_items=len(
                    normalized_selected
                ),
                error_code=None,
                error_message=None,
            )

            self.repository.update_run_status(
                run_id=run_id,
                status="RUNNING",
                current_stage=stage_name,
                progress_percentage=90,
                error_code=None,
                error_message=None,
            )

            return {
                **state,
                **legacy_output,
                "compliance_assessments": (
                    assessments
                ),
                "findings": (
                    compliance_findings
                ),
                "compliance_findings": (
                    compliance_findings
                ),
                "compliance_scores": (
                    compliance_scores
                ),
            }

        except Exception as error:
            safe_error = (
                "Compliance evaluation failed: "
                f"{error}"
            )

            self.repository.update_stage(
                run_id=run_id,
                stage_name=stage_name,
                stage_status="FAILED",
                message=(
                    "Compliance evaluation failed"
                ),
                error_code=(
                    "COMPLIANCE_EVALUATION_FAILED"
                ),
                error_message=safe_error,
            )

            self.repository.update_run_status(
                run_id=run_id,
                status="FAILED",
                current_stage=stage_name,
                progress_percentage=78,
                error_code=(
                    "COMPLIANCE_EVALUATION_FAILED"
                ),
                error_message=safe_error,
            )

            raise

    def _report(self, state: DiscoveryState):
        run_id = state["discovery_run_id"]

        self.repository.update_run_status(
            run_id=run_id,
            status="RUNNING",
            current_stage="REPORT_FINALIZATION",
            progress_percentage=95,
            error_code=None,
            error_message=None,
        )

        self.repository.update_stage(
            run_id=run_id,
            stage_name="REPORT_FINALIZATION",
            stage_status="RUNNING",
            message="Building discovery report",
            processed_items=0,
            total_items=1,
            error_code=None,
            error_message=None,
        )

        try:
            report = self.report_agent.build(state)

            self.repository.update_stage(
                run_id=run_id,
                stage_name="REPORT_FINALIZATION",
                stage_status="COMPLETED",
                message=(
                    "Discovery report completed"
                ),
                processed_items=1,
                total_items=1,
                error_code=None,
                error_message=None,
            )

            self.repository.update_run_status(
                run_id=run_id,
                status="SUCCEEDED",
                current_stage=(
                    "REPORT_FINALIZATION"
                ),
                progress_percentage=100,
                error_code=None,
                error_message=None,
            )

            return {
                **state,
                "report": report,
                "status": "SUCCEEDED",
            }

        except Exception as error:
            safe_error = (
                "Report finalization failed: "
                f"{error.__class__.__name__}"
            )

            self.repository.update_stage(
                run_id=run_id,
                stage_name="REPORT_FINALIZATION",
                stage_status="FAILED",
                message=(
                    "Report finalization failed"
                ),
                error_code=(
                    "REPORT_FINALIZATION_FAILED"
                ),
                error_message=safe_error,
            )

            self.repository.update_run_status(
                run_id=run_id,
                status="FAILED",
                current_stage=(
                    "REPORT_FINALIZATION"
                ),
                progress_percentage=95,
                error_code=(
                    "REPORT_FINALIZATION_FAILED"
                ),
                error_message=safe_error,
            )

            raise

    @staticmethod
    def _calculate_effective_scopes(
        requested_scopes,
    ):
        effective_scopes = []

        for scope in requested_scopes or []:
            normalized_scope = (
                str(scope).strip().upper()
            )

            if (
                normalized_scope
                and normalized_scope
                not in effective_scopes
            ):
                effective_scopes.append(
                    normalized_scope
                )

        requires_metadata = any(
            scope in effective_scopes
            for scope in {
                "COLUMN_CLASSIFICATION",
                "REGULATORY_COMPLIANCE",
                "HIPAA_COMPLIANCE",
                "DEPENDENCY_MAPPING",
                "DEPENDENCY_MAP",
            }
        )

        if (
            requires_metadata
            and "METADATA_PROFILING"
            not in effective_scopes
        ):
            effective_scopes.insert(
                0,
                "METADATA_PROFILING",
            )

        if (
            "REGULATORY_COMPLIANCE"
            in effective_scopes
            or "HIPAA_COMPLIANCE"
            in effective_scopes
        ):
            if (
                "COLUMN_CLASSIFICATION"
                not in effective_scopes
            ):
                metadata_index = (
                    effective_scopes.index(
                        "METADATA_PROFILING"
                    )
                    + 1
                )

                effective_scopes.insert(
                    metadata_index,
                    "COLUMN_CLASSIFICATION",
                )

        return effective_scopes

    def _build_graph(self):
        graph = StateGraph(DiscoveryState)

        graph.add_node(
            "metadata_and_profiling",
            self._metadata,
        )

        graph.add_node(
            "classification",
            self._classify,
        )

        graph.add_node(
            "dependency_mapping",
            self._dependencies,
        )

        graph.add_node(
            "compliance",
            self._compliance,
        )

        graph.add_node(
            "report",
            self._report,
        )

        graph.add_edge(
            START,
            "metadata_and_profiling",
        )

        graph.add_edge(
            "metadata_and_profiling",
            "classification",
        )

        graph.add_edge(
            "classification",
            "dependency_mapping",
        )

        graph.add_edge(
            "dependency_mapping",
            "compliance",
        )

        graph.add_edge(
            "compliance",
            "report",
        )

        graph.add_edge(
            "report",
            END,
        )

        return graph.compile()

    def invoke(
        self,
        discovery_run_id: str,
        connection_id: int,
        scopes: list[str],
        source_connection: Any,
        selected_objects=None,
        selected_frameworks=None,
    ):
        requested_scopes = [
            str(scope).strip().upper()
            for scope in scopes or []
            if str(scope).strip()
        ]

        effective_scopes = (
            self._calculate_effective_scopes(
                requested_scopes
            )
        )

        initial_state = self._initial_state(
            discovery_run_id=(
                discovery_run_id
            ),
            connection_id=connection_id,
            requested_scopes=(
                requested_scopes
            ),
            effective_scopes=(
                effective_scopes
            ),
            source_connection=(
                source_connection
            ),
            selected_objects=(
                selected_objects
            ),
            selected_frameworks=(
                selected_frameworks
            ),
        )

        return self.graph.invoke(
            initial_state
        )

    async def ainvoke(
        self,
        discovery_run_id: str,
        connection_id: int,
        scopes: list[str],
        source_connection: Any,
        selected_objects=None,
        selected_frameworks=None,
    ):
        requested_scopes = [
            str(scope).strip().upper()
            for scope in scopes or []
            if str(scope).strip()
        ]

        effective_scopes = (
            self._calculate_effective_scopes(
                requested_scopes
            )
        )

        initial_state = self._initial_state(
            discovery_run_id=(
                discovery_run_id
            ),
            connection_id=connection_id,
            requested_scopes=(
                requested_scopes
            ),
            effective_scopes=(
                effective_scopes
            ),
            source_connection=(
                source_connection
            ),
            selected_objects=(
                selected_objects
            ),
            selected_frameworks=(
                selected_frameworks
            ),
        )

        return await self.graph.ainvoke(
            initial_state
        )

    @staticmethod
    def _initial_state(
        discovery_run_id,
        connection_id,
        requested_scopes,
        effective_scopes,
        source_connection,
        selected_objects,
        selected_frameworks,
    ):
        normalized_objects = []

        for selected_object in (
            selected_objects or []
        ):
            if not isinstance(
                selected_object,
                dict,
            ):
                continue

            object_name = str(
                selected_object.get(
                    "object_name"
                )
                or ""
            ).strip()

            object_type = str(
                selected_object.get(
                    "object_type"
                )
                or ""
            ).strip().upper()

            schema_name = str(
                selected_object.get(
                    "schema_name"
                )
                or ""
            ).strip()

            if not object_name or not object_type:
                continue

            normalized_object = {
                "object_name": object_name,
                "object_type": object_type,
            }

            if schema_name:
                normalized_object[
                    "schema_name"
                ] = schema_name

            normalized_objects.append(
                normalized_object
            )

        framework_codes = []

        for framework in (
            selected_frameworks or []
        ):
            normalized_framework = (
                str(framework)
                .strip()
                .upper()
            )

            if (
                normalized_framework
                and normalized_framework
                not in framework_codes
            ):
                framework_codes.append(
                    normalized_framework
                )

        if (
            "HIPAA_COMPLIANCE"
            in effective_scopes
            and "HIPAA"
            not in framework_codes
        ):
            framework_codes.append("HIPAA")

        return {
            "discovery_run_id": (
                discovery_run_id
            ),
            "connection_id": connection_id,
            "requested_scopes": (
                requested_scopes
            ),
            "effective_scopes": (
                effective_scopes
            ),
            "selected_objects": (
                normalized_objects
            ),
            "selected_frameworks": (
                framework_codes
            ),
            "source_connection": (
                source_connection
            ),
            "errors": [],
            "status": "PENDING",
        }