from typing import Any, TypedDict


class DiscoveryState(TypedDict, total=False):
    discovery_run_id: str
    connection_id: int
    requested_scopes: list[str]
    effective_scopes: list[str]
    source_connection: Any

    objects: list[dict]
    table_profiles: list[dict]
    column_profiles: list[dict]

    classifications: list[Any]
    classification_records: list[dict]

    dependencies: list[Any]
    dependency_records: list[dict]

    hipaa_findings: list[Any]
    hipaa_finding_records: list[dict]
    hipaa_score: Any
    hipaa_score_id: int

    report: dict
    errors: list[dict]
    status: str