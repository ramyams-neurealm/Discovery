from src.tools.access_policy_evaluator import (
    evaluate_database_access_policy,
)


def _evidence(privileges):
    return [{
        "evidence_type": "DATABASE_PERMISSIONS",
        "source": "MYSQL_USER_PRIVILEGES",
        "scope": "GLOBAL",
        "database_name": "premier",
        "collection_status": "COLLECTED",
        "records": [
            {
                "principal": "'neustream'@'%'",
                "privilege_type": privilege,
            }
            for privilege in privileges
        ],
    }]


def _policy(allowed):
    return [{
        "client_policy_id": 1,
        "principal_selector_type": "CLIENT_PRINCIPAL_GROUP",
        "principal_selector_value": "clinical_roles",
        "principal_names": ["neustream"],
        "allowed_privileges": allowed,
        "effect": "ALLOW",
        "priority": 100,
        "connection_id": None,
        "evaluated_connection_id": 14,
    }]


def test_access_policy_passes_allowed_select():
    status, _, _, review, details = evaluate_database_access_policy(
        _evidence(["SELECT"]), _policy(["SELECT"])
    )
    assert status == "PASS"
    assert review is False
    assert len(details["matched"]) == 1


def test_access_policy_fails_unapproved_update():
    status, explanation, _, review, details = (
        evaluate_database_access_policy(
            _evidence(["SELECT", "UPDATE"]),
            _policy(["SELECT"]),
        )
    )
    assert status == "FAIL"
    assert "UPDATE" in explanation
    assert review is True
    assert len(details["violations"]) == 1


def test_access_policy_without_context_is_partial():
    status, _, _, review, _ = evaluate_database_access_policy(
        _evidence(["SELECT"]), []
    )
    assert status == "PARTIAL"
    assert review is True
