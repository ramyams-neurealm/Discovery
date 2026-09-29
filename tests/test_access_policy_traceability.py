from src.tools.access_policy_evaluator import (
    evaluate_database_access_policy,
)


def test_trace_contains_allowed_and_violating_privileges():
    evidence = [{
        "evidence_type": "DATABASE_PERMISSIONS",
        "source": "MYSQL_USER_PRIVILEGES",
        "scope": "GLOBAL",
        "database_name": "premier",
        "collection_status": "COLLECTED",
        "records": [
            {
                "principal": "'neustream'@'%'",
                "privilege_type": "SELECT",
            },
            {
                "principal": "'neustream'@'%'",
                "privilege_type": "UPDATE",
            },
        ],
    }]
    policies = [{
        "client_policy_id": 1,
        "principal_selector_type": "CLIENT_PRINCIPAL_GROUP",
        "principal_names": ["neustream"],
        "allowed_privileges": ["SELECT"],
        "effect": "ALLOW",
        "priority": 100,
        "connection_id": None,
        "evaluated_connection_id": 14,
    }]

    status, _, _, _, trace = evaluate_database_access_policy(
        evidence, policies
    )

    assert status == "FAIL"
    assert trace["matched"][0]["privilege"] == "SELECT"
    assert trace["matched"][0]["policy_ids"] == [1]
    assert trace["violations"][0]["privilege"] == "UPDATE"
