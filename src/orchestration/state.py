from __future__ import annotations

from typing import Any, TypedDict


class DiscoveryState(TypedDict, total=False):
    # Discovery run configuration
    discovery_run_id: str
    connection_id: int
    requested_scopes: list[str]
    effective_scopes: list[str]
    selected_objects: list[dict[str, str]]
    selected_frameworks: list[str]
    source_connection: Any

    # Metadata discovery and profiling
    metadata_profile: dict[str, Any]
    objects: list[dict[str, Any]]
    table_profiles: list[dict[str, Any]]
    column_profiles: list[dict[str, Any]]
    profile_errors: list[Any]
    metadata_error: str | None

    # Column classification
    classifications: list[Any]
    classification_records: list[dict[str, Any]]
    classification_summary: dict[str, Any]

    # Dependency mapping
    dependencies: list[Any]
    dependency_records: list[dict[str, Any]]

    # Generic compliance results
    compliance_assessments: dict[str, Any]
    compliance_findings: list[Any]
    compliance_scores: dict[str, Any]
    findings: list[Any]

    # HIPAA compliance
    hipaa_findings: list[Any]
    hipaa_finding_records: list[dict[str, Any]]
    hipaa_score: Any
    hipaa_score_id: int | None
    generic_hipaa_result: Any

    # GDPR compliance
    gdpr_findings: list[Any]
    gdpr_score: Any

    # PCI DSS compliance
    pci_dss_findings: list[Any]
    pci_dss_score: Any

    # GLBA compliance
    glba_findings: list[Any]
    glba_score: Any

    # DPDP compliance
    dpdp_findings: list[Any]
    dpdp_score: Any

    # CCPA / CPRA compliance
    ccpa_findings: list[Any]
    ccpa_score: Any

    # PIPEDA compliance
    pipeda_findings: list[Any]
    pipeda_score: Any

    # Report and workflow status
    report: dict[str, Any]
    errors: list[dict[str, Any]]
    status: str