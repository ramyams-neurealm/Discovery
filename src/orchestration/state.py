from typing import Any, TypedDict


class DiscoveryState(TypedDict, total=False):
    discovery_run_id: str
    connection_id: int
    requested_scopes: list[str]
    effective_scopes: list[str]
    selected_objects: list[dict[str, str]]
    selected_frameworks: list[str]
    source_connection: Any
    objects: list[dict[str, Any]]
    table_profiles: list[dict[str, Any]]
    column_profiles: list[dict[str, Any]]
    classifications: list[Any]
    classification_records: list[dict[str, Any]]
    classification_summary: dict[str, Any]
    dependencies: list[Any]
    dependency_records: list[dict[str, Any]]
    hipaa_findings: list[Any]
    hipaa_finding_records: list[dict[str, Any]]
    hipaa_score: Any
    hipaa_score_id: int
    report: dict[str, Any]
    errors: list[dict[str, Any]]
    status: str
