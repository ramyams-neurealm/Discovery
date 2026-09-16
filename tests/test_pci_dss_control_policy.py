import importlib.util
from pathlib import Path

MODULE_PATH = Path(__file__).with_name("pci_dss_control_policy.py")
spec = importlib.util.spec_from_file_location(
    "pci_dss_control_policy", MODULE_PATH
)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
evaluate_pci_dss_controls = module.evaluate_pci_dss_controls


def controls():
    definitions = [
        ("PCI-DATA-001", "CARD_DATA_DISCOVERY", "COLUMN_CLASSIFICATION"),
        ("PCI-STORAGE-001", "EVIDENCE_REQUIRED", "STORAGE_PROTECTION"),
        ("PCI-ACCESS-001", "EVIDENCE_REQUIRED", "DATABASE_PERMISSIONS"),
        ("PCI-TRANS-001", "EVIDENCE_REQUIRED", "TRANSMISSION_SECURITY"),
        ("PCI-AUDIT-001", "EVIDENCE_REQUIRED", "AUDIT_CONFIGURATION"),
        ("PCI-VULN-001", "EVIDENCE_REQUIRED", "VULNERABILITY_MANAGEMENT"),
        ("PCI-TEST-001", "EVIDENCE_REQUIRED", "SECURITY_TEST_RECORD"),
    ]
    return [
        {
            "control_code": code,
            "control_title": code,
            "evaluation_type": evaluation,
            "evidence_type": evidence,
            "default_severity": "NEEDS_REVIEW",
        }
        for code, evaluation, evidence in definitions
    ]


def test_credit_card_number_triggers_pci_dss():
    results, summary = evaluate_pci_dss_controls(
        controls(),
        [{
            "display_classification": "FINANCIAL",
            "sensitive_data_type": "CREDIT_CARD_NUMBER",
            "is_sensitive": True,
            "confidence": 0.96,
            "needs_human_review": False,
        }],
    )
    assert summary["card_data_columns_checked"] == 1
    assert summary["applicable_controls"] == 7
    assert summary["assessed_controls"] == 1
    assert summary["evidence_coverage"] == 14.29
    assert summary["score"] is None
    assert summary["risk_band"] == "INSUFFICIENT_EVIDENCE"
    assert sum(r["assessment_status"] == "PASS" for r in results) == 1
    assert sum(
        r["assessment_status"] == "INSUFFICIENT_EVIDENCE"
        for r in results
    ) == 6


def test_bank_account_number_does_not_trigger_pci_dss():
    results, summary = evaluate_pci_dss_controls(
        controls(),
        [{
            "display_classification": "FINANCIAL",
            "sensitive_data_type": "BANK_ACCOUNT_NUMBER",
            "is_sensitive": True,
            "confidence": 0.95,
            "needs_human_review": False,
        }],
    )
    assert summary["applicable_controls"] == 0
    assert summary["risk_band"] == "NOT_APPLICABLE"
    assert all(
        row["assessment_status"] == "NOT_APPLICABLE"
        for row in results
    )
