from __future__ import annotations

from typing import Any


DATA_ACCESS_PRIVILEGES = {
    "SELECT", "INSERT", "UPDATE", "DELETE", "REFERENCES",
    "EXECUTE", "ALTER", "ALTER ROUTINE", "CREATE", "CREATE VIEW",
    "CREATE ROUTINE", "DROP", "INDEX", "TRIGGER",
}


def _value(value: Any) -> str:
    return str(getattr(value, "value", value) or "").strip().upper()


def _principal_name(value: Any) -> str:
    raw = str(value or "").strip()
    if "@" in raw:
        raw = raw.rsplit("@", 1)[0]
    return raw.strip("'`").lower()


def evaluate_database_access_policy(
    security_evidence: list[dict[str, Any]],
    policy_context: list[dict[str, Any]],
) -> tuple[str, str, float, bool, dict[str, Any]]:
    """Compare observed DB privileges with effective client policies."""
    groups = [
        item for item in security_evidence
        if _value(item.get("evidence_type")) == "DATABASE_PERMISSIONS"
    ]
    if not groups:
        return (
            "INSUFFICIENT_EVIDENCE",
            "Database permission evidence was not collected.",
            1.0,
            True,
            {"matched": [], "violations": []},
        )

    failed = [
        item for item in groups
        if _value(item.get("collection_status")) in {
            "PERMISSION_DENIED", "COLLECTION_FAILED"
        }
    ]
    records: list[dict[str, Any]] = []
    for item in groups:
        if _value(item.get("collection_status")) != "COLLECTED":
            continue
        if _value(item.get("scope")) not in {
            "GLOBAL", "SCHEMA", "TABLE", "COLUMN"
        }:
            continue
        for record in item.get("records") or []:
            privilege = _value(record.get("privilege_type"))
            principal = _principal_name(record.get("principal"))
            if not principal or principal.startswith("mysql."):
                continue
            if privilege not in DATA_ACCESS_PRIVILEGES:
                continue
            records.append({
                "principal": principal,
                "privilege": privilege,
                "scope": _value(item.get("scope")),
                "schema_name": record.get("schema_name")
                or item.get("database_name"),
                "table_name": record.get("table_name"),
                "column_name": record.get("column_name"),
                "source": item.get("source"),
            })

    if not records:
        failed_sources = ", ".join(
            sorted(
                str(item.get("source") or "UNKNOWN")
                for item in failed
            )
        )
        suffix = (
            f" Collection failed for: {failed_sources}."
            if failed_sources
            else ""
        )
        return (
            "INSUFFICIENT_EVIDENCE",
            "No usable data-access privilege records were collected."
            + suffix,
            1.0,
            True,
            {"matched": [], "violations": []},
        )
    if not policy_context:
        principals = {
            record["principal"]
            for record in records
            if record.get("principal")
        }
        return (
            "PARTIAL",
            f"Collected {len(records)} database permission record(s) for "
            f"{len(principals)} principal(s), but no active client "
            "DATA_ACCESS policy context was supplied. Approved-principal "
            "and least-privilege compliance still require review.",
            1.0,
            True,
            {"matched": [], "violations": records},
        )

    matched: list[dict[str, Any]] = []
    violations: list[dict[str, Any]] = []
    for record in records:
        applicable = []
        for policy in policy_context:
            members = {
                str(name).strip().lower()
                for name in policy.get("principal_names", [])
            }
            selector_type = _value(policy.get("principal_selector_type"))
            principal_matches = (
                selector_type == "ALL_PRINCIPALS"
                or record["principal"] in members
                or (
                    selector_type == "EXACT_PRINCIPAL"
                    and record["principal"]
                    == str(policy.get("principal_selector_value") or "")
                    .strip().lower()
                )
            )
            connection_matches = (
                policy.get("connection_id") is None
                or policy.get("connection_id")
                == policy.get("evaluated_connection_id")
            )
            if principal_matches and connection_matches:
                applicable.append(policy)

        allowed = False
        matched_policy_ids: list[int] = []
        for policy in sorted(
            applicable,
            key=lambda item: int(item.get("priority") or 0),
            reverse=True,
        ):
            if _value(policy.get("effect")) == "DENY":
                allowed = False
                matched_policy_ids.append(int(policy["client_policy_id"]))
                break
            privileges = {
                _value(item) for item in policy.get("allowed_privileges", [])
            }
            if record["privilege"] in privileges:
                allowed = True
                matched_policy_ids.append(int(policy["client_policy_id"]))
                break

        result = {**record, "policy_ids": matched_policy_ids}
        if allowed:
            matched.append(result)
        else:
            violations.append(result)

    details = {"matched": matched, "violations": violations}
    if violations:
        sample = ", ".join(
            f"{item['principal']}:{item['privilege']}"
            for item in violations[:8]
        )
        return (
            "FAIL",
            f"Found {len(violations)} privilege assignment(s) outside the "
            f"active PHI access policy. Examples: {sample}.",
            1.0,
            True,
            details,
        )
    return (
        "PASS",
        f"All {len(matched)} observed data-access privilege assignment(s) "
        "are allowed by an active PHI access policy.",
        1.0,
        False,
        details,
    )
