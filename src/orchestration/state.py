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
    dependencies: list[Any]
    hipaa_findings: list[Any]
    hipaa_score: Any
    report: dict
    errors: list[dict]
    status: str
