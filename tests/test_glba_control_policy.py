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
    """
    Proves that BANK_ACCOUNT_NUMBER makes GLBA applicable, 
    and that missing evidence results in INSUFFICIENT_EVIDENCE, not FAIL.
    """
    classifications = [
        {
            "column_name": "account_number",
            "is_sensitive": True,
            "sensitive_data_type": "BANK_ACCOUNT_NUMBER", # Establishes applicability
            "confidence": 0.95
        }
    ]

    results, summary = evaluate_glba_controls(sample_controls, classifications)

    # 1. Verify DATA-001 passes because financial data was discovered
    data_control = next(r for r in results if r["control_code"] == "GLBA-DATA-001")
    assert data_control["assessment_status"] == "PASS"

    # 2. Verify ACCESS-001 becomes INSUFFICIENT_EVIDENCE (NOT FAIL) due to missing evidence
    access_control = next(r for r in results if r["control_code"] == "GLBA-ACCESS-001")
    assert access_control["assessment_status"] == "INSUFFICIENT_EVIDENCE"
    assert access_control["assessment_status"] != "FAIL"
    assert access_control["needs_human_review"] is True

    # 3. Verify scoring guardrails (coverage is exactly 50% because 1 of 2 controls is assessed/passed)
    assert summary["applicable_controls"] == 2
    assert summary["assessed_controls"] == 1
    assert summary["evidence_coverage"] == 50.0
    assert summary["score"] == 100.0  # 1 PASS / 1 Assessed

def test_glba_insufficient_coverage_null_score(sample_controls):
    """
    Proves that if evidence coverage is below 50%, the score is Null.
    """
    # Add a third control so coverage drops to 33.3% (1 out of 3 assessed)
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
            "sensitive_data_type": "FINANCIAL",
            "confidence": 0.90
        }
    ]

    results, summary = evaluate_glba_controls(sample_controls, classifications)

    # Coverage is 1/3 (33.33%), which is < 50%
    assert summary["evidence_coverage"] < 50.0
    
    # Score must be None and risk band must reflect insufficient evidence
    assert summary["score"] is None
    assert summary["risk_band"] == "INSUFFICIENT_EVIDENCE"

def test_glba_not_applicable(sample_controls):
    """
    Proves that without banking classifications, GLBA is NOT_APPLICABLE.
    """
    classifications = [
        {
            "column_name": "patient_health_record",
            "is_sensitive": True,
            "sensitive_data_type": "PHI", # Not a GLBA trigger
            "confidence": 0.99
        }
    ]

    results, summary = evaluate_glba_controls(sample_controls, classifications)

    for r in results:
        assert r["assessment_status"] == "NOT_APPLICABLE"

    assert summary["risk_band"] == "NOT_APPLICABLE"
    assert summary["applicable_controls"] == 0
    assert summary["score"] is None