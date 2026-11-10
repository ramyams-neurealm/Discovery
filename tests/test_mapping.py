import pytest
from src.policies.compliance_mapping import (
    filter_columns_for_framework,
    map_column_to_frameworks,
)

# Simulated Stage 3 classified columns
test_columns = [
    {
        "column_name": "pt_ssn",
        "display_classification": "PII",
        "sensitive_data_type": "SOCIAL_SECURITY_NUMBER",
        "is_sensitive": True,
    },
    {
        "column_name": "dob",
        "display_classification": "PII",
        "sensitive_data_type": "DATE_OF_BIRTH",
        "is_sensitive": True,
    },
    {
        "column_name": "card_number",
        "display_classification": "FINANCIAL",
        "sensitive_data_type": "CREDIT_CARD_NUMBER",
        "is_sensitive": True,
    },
    {
        "column_name": "mrn_id",
        "display_classification": "PHI",
        "sensitive_data_type": "MEDICAL_RECORD_NUMBER",
        "is_sensitive": True,
    },
    {
        "column_name": "incremental_type",
        "display_classification": "PUBLIC",
        "sensitive_data_type": "NONE",
        "is_sensitive": False,
    },
]


def test_map_column_to_frameworks_phi():
    matched = map_column_to_frameworks(
        display_classification="PHI",
        is_sensitive=True,
    )
    assert "HIPAA" in matched
    assert "GDPR" in matched
    # CCPA statutorily carves out HIPAA-governed PHI
    assert "CCPA" not in matched


def test_map_column_to_frameworks_financial():
    matched = map_column_to_frameworks(
        display_classification="FINANCIAL",
        is_sensitive=True,
    )
    assert "PCI_DSS" in matched
    assert "GLBA" in matched
    assert "GDPR" in matched
    assert "HIPAA" not in matched


def test_map_column_public_not_sensitive():
    matched = map_column_to_frameworks(
        display_classification="PUBLIC",
        is_sensitive=False,
    )
    assert matched == []


def test_filter_columns_for_hipaa():
    hipaa_cols = filter_columns_for_framework("HIPAA", test_columns)
    column_names = [c["column_name"] for c in hipaa_cols]
    assert column_names == ["mrn_id"]


def test_filter_columns_for_pci_dss():
    pci_cols = filter_columns_for_framework("PCI_DSS", test_columns)
    column_names = [c["column_name"] for c in pci_cols]
    assert column_names == ["card_number"]


def test_filter_columns_for_gdpr():
    gdpr_cols = filter_columns_for_framework("GDPR", test_columns)
    column_names = [c["column_name"] for c in gdpr_cols]
    # GDPR covers PII, PHI, FINANCIAL, SENSITIVE
    assert set(column_names) == {"pt_ssn", "dob", "card_number", "mrn_id"}