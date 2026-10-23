from src.policies.compliance_mapping import (
    filter_columns_for_framework,
    map_column_to_frameworks,
)

# Simulated Stage 3 outputs
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

print("--- Testing map_column_to_frameworks ---")
for col in test_columns:
    frameworks = map_column_to_frameworks(
        display_classification=col["display_classification"],
        sensitive_data_type=col["sensitive_data_type"],
        is_sensitive=col["is_sensitive"],
    )
    print(f"Column '{col['column_name']}': {frameworks}")

print("\n--- Testing filter_columns_for_framework ---")
hipaa_cols = filter_columns_for_framework("HIPAA", test_columns)
pci_cols = filter_columns_for_framework("PCI_DSS", test_columns)

print(f"HIPAA In-Scope: {[c['column_name'] for c in hipaa_cols]}")
print(f"PCI_DSS In-Scope: {[c['column_name'] for c in pci_cols]}")