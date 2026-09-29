import pytest

from src.tools.hipaa_control_policy import evaluate_hipaa_controls


@pytest.fixture
def sample_controls():
    return [
        {
            "control_code": "HIPAA-DATA-001",
            "control_title": "Identify electronic protected health information",
            "evaluation_type": "PHI_DISCOVERY",
            "evidence_type": "COLUMN_CLASSIFICATION",
            "default_severity": "NEEDS_REVIEW",
        },
        {
            "control_code": "HIPAA-ACCESS-001",
            "control_title": "Verify access controls",
            "evaluation_type": "EVIDENCE_REQUIRED",
            "evidence_type": "DATABASE_PERMISSIONS",
            "default_severity": "NEEDS_REVIEW",
        },
    ]


@pytest.fixture
def phi_classifications():
    return [
        {
            "schema_name": "hospital",
            "table_name": "patients",
            "column_name": "ssn",
            "display_classification": "PHI",
            "confidence": 0.98,
            "needs_human_review": False,
        }
    ]


def test_hipaa_phi_with_missing_access_evidence(
    sample_controls,
    phi_classifications,
):
    """PHI applies, while absent access evidence is insufficient evidence."""
    results, summary = evaluate_hipaa_controls(
        sample_controls,
        phi_classifications,
    )

    data_control = next(
        result
        for result in results
        if result["control_code"] == "HIPAA-DATA-001"
    )
    access_control = next(
        result
        for result in results
        if result["control_code"] == "HIPAA-ACCESS-001"
    )

    assert data_control["assessment_status"] == "PASS"
    assert access_control["assessment_status"] == "INSUFFICIENT_EVIDENCE"
    assert access_control["needs_human_review"] is True

    assert summary["applicable_controls"] == 2
    assert summary["assessed_controls"] == 1
    assert summary["evidence_coverage"] == 50.0
    assert summary["score"] == 100.0


def test_hipaa_collected_access_evidence_is_partial(
    sample_controls,
    phi_classifications,
):
    """Collected grants become PARTIAL until approved principals are known."""
    security_evidence = [
        {
            "evidence_type": "DATABASE_PERMISSIONS",
            "source": "MYSQL_CURRENT_ACCOUNT",
            "scope": "SESSION",
            "database_name": "hospital",
            "collection_status": "COLLECTED",
            "record_count": 1,
            "records": [
                {
                    "authenticated_account": "discovery_user@%",
                    "connected_account": "discovery_user@localhost",
                    "active_roles": "NONE",
                }
            ],
        },
        {
            "evidence_type": "DATABASE_PERMISSIONS",
            "source": "MYSQL_TABLE_PRIVILEGES",
            "scope": "TABLE",
            "database_name": "hospital",
            "collection_status": "COLLECTED",
            "record_count": 2,
            "records": [
                {
                    "principal": "'clinical_user'@'%'",
                    "schema_name": "hospital",
                    "table_name": "patients",
                    "privilege_type": "SELECT",
                    "is_grantable": "NO",
                },
                {
                    "principal": "'analytics_user'@'%'",
                    "schema_name": "hospital",
                    "table_name": "patients",
                    "privilege_type": "SELECT",
                    "is_grantable": "NO",
                },
            ],
        },
    ]

    results, summary = evaluate_hipaa_controls(
        sample_controls,
        phi_classifications,
        security_evidence,
    )

    access_control = next(
        result
        for result in results
        if result["control_code"] == "HIPAA-ACCESS-001"
    )

    assert access_control["assessment_status"] == "PARTIAL"
    assert access_control["needs_human_review"] is True
    assert "2 database permission record(s)" in access_control["explanation"]
    assert "2 principal(s)" in access_control["explanation"]

    assert summary["applicable_controls"] == 2
    assert summary["assessed_controls"] == 2
    assert summary["evidence_coverage"] == 100.0
    assert summary["score"] == 75.0
    assert summary["risk_band"] == "NEEDS_REVIEW"


def test_hipaa_permission_collection_failure_is_insufficient(
    sample_controls,
    phi_classifications,
):
    """Collector failure must not be treated as a compliance failure."""
    security_evidence = [
        {
            "evidence_type": "DATABASE_PERMISSIONS",
            "source": "MYSQL_TABLE_PRIVILEGES",
            "scope": "TABLE",
            "database_name": "hospital",
            "collection_status": "PERMISSION_DENIED",
            "record_count": 0,
            "records": [],
            "error_type": "ProgrammingError",
        }
    ]

    results, summary = evaluate_hipaa_controls(
        sample_controls,
        phi_classifications,
        security_evidence,
    )

    access_control = next(
        result
        for result in results
        if result["control_code"] == "HIPAA-ACCESS-001"
    )

    assert access_control["assessment_status"] == "INSUFFICIENT_EVIDENCE"
    assert access_control["assessment_status"] != "FAIL"
    assert access_control["needs_human_review"] is True
    assert "MYSQL_TABLE_PRIVILEGES" in access_control["explanation"]

    assert summary["applicable_controls"] == 2
    assert summary["assessed_controls"] == 1
    assert summary["evidence_coverage"] == 50.0


def test_hipaa_not_applicable_without_phi(sample_controls):
    """Without PHI classifications, HIPAA controls are not applicable."""
    classifications = [
        {
            "schema_name": "hospital",
            "table_name": "departments",
            "column_name": "department_name",
            "display_classification": "PUBLIC",
            "confidence": 0.99,
            "needs_human_review": False,
        }
    ]

    results, summary = evaluate_hipaa_controls(
        sample_controls,
        classifications,
    )

    for result in results:
        assert result["assessment_status"] == "NOT_APPLICABLE"

    assert summary["applicable_controls"] == 0
    assert summary["risk_band"] == "NOT_APPLICABLE"
    assert summary["score"] is None
