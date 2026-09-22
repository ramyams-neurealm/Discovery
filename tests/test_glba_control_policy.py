import pytest
from src.tools.glba_control_policy import evaluate_glba_controls

@pytest.fixture
def sample_controls():
    return [
        {
            "control_code": "GLBA-DATA-001",
            "control_title": "Identify stored financial data",
            "evaluation_type": "FINANCIAL_DATA_DISCOVERY",
            "evidence_type": "COLUMN_CLASSIFICATION"
        },
        {
            "control_code": "GLBA-ACCESS-001",
            "control_title": "Verify access restrictions",
            "evaluation_type": "EVIDENCE_REQUIRED",
            "evidence_type": "DATABASE_PERMISSIONS"
        }
    ]

def test_glba_applicability_and_missing_evidence(sample_controls):
    classifications = [
        {
            "column_name": "account_number",
            "is_sensitive": True,
            "sensitive_data_type": "BANK_ACCOUNT_NUMBER",
            "confidence": 0.95
        }
    ]

    results, summary = evaluate_glba_controls(sample_controls, classifications)

    data_control = next(r for r in results if r["control_code"] == "GLBA-DATA-001")
    assert data_control["assessment_status"] == "PASS"

    access_control = next(r for r in results if r["control_code"] == "GLBA-ACCESS-001")
    assert access_control["assessment_status"] == "INSUFFICIENT_EVIDENCE"
    assert access_control["needs_human_review"] is True

    assert summary["applicable_controls"] == 2
    assert summary["assessed_controls"] == 1
    assert summary["evidence_coverage"] == 50.0
    assert summary["score"] == 100.0

def test_glba_insufficient_coverage_null_score(sample_controls):
    sample_controls.append({
        "control_code": "GLBA-TRANS-001",
        "control_title": "Verify transmission protection",
        "evaluation_type": "EVIDENCE_REQUIRED",
        "evidence_type": "TRANSMISSION_SECURITY"
    })
    
    classifications = [
        {
            "column_name": "routing_number",
            "is_sensitive": True,
            "sensitive_data_type": "BANK_ACCOUNT_NUMBER",
            "confidence": 0.90
        }
    ]

    results, summary = evaluate_glba_controls(sample_controls, classifications)

    assert summary["evidence_coverage"] < 50.0
    assert summary["score"] is None
    assert summary["risk_band"] == "INSUFFICIENT_EVIDENCE"

def test_glba_not_applicable(sample_controls):
    classifications = [
        {
            "column_name": "patient_health_record",
            "is_sensitive": True,
            "sensitive_data_type": "PHI",
            "confidence": 0.99
        }
    ]

    results, summary = evaluate_glba_controls(sample_controls, classifications)

    for r in results:
        assert r["assessment_status"] == "NOT_APPLICABLE"

    assert summary["risk_band"] == "NOT_APPLICABLE"
    assert summary["applicable_controls"] == 0
    assert summary["score"] is None