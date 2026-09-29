from __future__ import annotations

from typing import Any

from src.models.compliance_foundation import (
    EvidenceCategory,
    EvidenceCollectionStatus,
    EvidencePrincipal,
    EvidenceResource,
    EvidenceSourceType,
    NormalizedEvidence,
    PrincipalType,
)


def _clean_principal(value: Any) -> tuple[str | None, str | None]:
    """Normalize MySQL's quoted 'user'@'host' account representation."""
    raw = str(value or "").strip()
    if not raw:
        return None, None
    if "@" not in raw:
        return raw.strip("'`"), None
    name, host = raw.rsplit("@", 1)
    return name.strip("'`"), host.strip("'`")


def normalize_mysql_access_evidence(
    raw_evidence: list[dict[str, Any]],
    *,
    tenant_id: int,
    connection_id: int,
    discovery_run_id: str,
) -> list[NormalizedEvidence]:
    """Convert grouped MySQL collector output into reusable observations."""
    normalized: list[NormalizedEvidence] = []

    for group in raw_evidence:
        source = str(group.get("source") or "MYSQL_UNKNOWN")
        scope = str(group.get("scope") or "UNKNOWN").upper()
        database_name = str(group.get("database_name") or "") or None
        status = EvidenceCollectionStatus(
            str(group.get("collection_status") or "COLLECTION_FAILED")
        )
        records = list(group.get("records") or [])

        if not records:
            normalized.append(
                NormalizedEvidence(
                    tenant_id=tenant_id,
                    connection_id=connection_id,
                    discovery_run_id=discovery_run_id,
                    evidence_category=EvidenceCategory.DATABASE_PERMISSIONS,
                    evidence_type="DATABASE_PERMISSION_COLLECTION",
                    source_type=EvidenceSourceType.DATABASE,
                    source_system="MYSQL",
                    collector_name="mysql_permission_collector",
                    collector_version="1.1",
                    resource=EvidenceResource(
                        resource_type=scope,
                        schema_name=database_name,
                        qualified_name=database_name,
                    ),
                    observation={
                        "scope": scope,
                        "record_count": 0,
                    },
                    collection_status=status,
                    raw_reference={"source_view": source},
                    error=(
                        {"error_type": group.get("error_type")}
                        if group.get("error_type")
                        else None
                    ),
                )
            )
            continue

        for record in records:
            if scope == "SESSION":
                account, host = _clean_principal(
                    record.get("authenticated_account")
                )
                normalized.append(
                    NormalizedEvidence(
                        tenant_id=tenant_id,
                        connection_id=connection_id,
                        discovery_run_id=discovery_run_id,
                        evidence_category=(
                            EvidenceCategory.DATABASE_PERMISSIONS
                        ),
                        evidence_type="DATABASE_ACCOUNT_CONTEXT",
                        source_type=EvidenceSourceType.DATABASE,
                        source_system="MYSQL",
                        collector_name="mysql_permission_collector",
                        collector_version="1.1",
                        principal=EvidencePrincipal(
                            principal_type=PrincipalType.DATABASE_USER,
                            principal_name=account,
                            principal_host=host,
                            principal_source="MYSQL",
                        ),
                        resource=EvidenceResource(
                            resource_type="SESSION",
                            schema_name=database_name,
                            qualified_name=database_name,
                        ),
                        observation={
                            "connected_account": record.get(
                                "connected_account"
                            ),
                            "active_roles": record.get("active_roles"),
                        },
                        collection_status=status,
                        raw_reference={"source_view": source},
                    )
                )
                continue

            principal_name, principal_host = _clean_principal(
                record.get("principal")
            )
            schema_name = record.get("schema_name") or database_name
            table_name = record.get("table_name")
            column_name = record.get("column_name")
            qualified_parts = [
                str(value)
                for value in (schema_name, table_name, column_name)
                if value
            ]
            normalized.append(
                NormalizedEvidence(
                    tenant_id=tenant_id,
                    connection_id=connection_id,
                    discovery_run_id=discovery_run_id,
                    evidence_category=EvidenceCategory.DATABASE_PERMISSIONS,
                    evidence_type="DATABASE_PERMISSION",
                    source_type=EvidenceSourceType.DATABASE,
                    source_system="MYSQL",
                    collector_name="mysql_permission_collector",
                    collector_version="1.1",
                    principal=EvidencePrincipal(
                        principal_type=PrincipalType.DATABASE_USER,
                        principal_name=principal_name,
                        principal_host=principal_host,
                        principal_source="MYSQL",
                    ),
                    resource=EvidenceResource(
                        resource_type=scope,
                        schema_name=schema_name,
                        table_name=table_name,
                        column_name=column_name,
                        qualified_name=".".join(qualified_parts) or None,
                    ),
                    observation={
                        "privilege": record.get("privilege_type"),
                        "grantable": (
                            str(record.get("is_grantable") or "").upper()
                            == "YES"
                        ),
                        "scope": scope,
                        "inherited": scope in {"GLOBAL", "SCHEMA"},
                        "inherited_from": scope,
                    },
                    collection_status=status,
                    raw_reference={"source_view": source},
                )
            )

    return normalized
