from typing import Any

# Specific type sets to prevent false alarms or missed statutory scopes
PCI_CARDHOLDER_TYPES = {
    "CREDIT_CARD_NUMBER",
    "BANK_ACCOUNT_NUMBER",
}

GLBA_FINANCIAL_TYPES = {
    "BANK_ACCOUNT_NUMBER",
    "FINANCIAL_INFORMATION",
    "FINANCIAL_AMOUNT",
    "PAYMENT_IDENTIFIER",
    "INVOICE_IDENTIFIER",
    "SOCIAL_SECURITY_NUMBER",
    "TAX_IDENTIFIER",
}

HIPAA_SPECIFIC_TYPES = {
    "MEDICAL_RECORD_NUMBER",
    "HEALTH_INFORMATION",
    "CLAIM_IDENTIFIER",
    "CLAIM_LINE_IDENTIFIER",
    "SERVICE_DATE",
    "PROCEDURE_CODE",
    "DIAGNOSIS_CODE",
    "DATE_OF_BIRTH",
    "SOCIAL_SECURITY_NUMBER",
}

# The 7 target frameworks and their statutory category boundaries
FRAMEWORK_SCOPES: dict[str, dict[str, set[str]]] = {
    "HIPAA": {
        "allowed_categories": {"PHI"},
        "extra_allowed_types": HIPAA_SPECIFIC_TYPES,
    },
    "GDPR": {
        "allowed_categories": {"PII", "PHI", "FINANCIAL", "SENSITIVE"},
        "extra_allowed_types": set(),
    },
    "DPDP": {
        "allowed_categories": {"PII", "PHI", "FINANCIAL", "SENSITIVE"},
        "extra_allowed_types": set(),
    },
    "CCPA": {
        "allowed_categories": {"PII", "FINANCIAL", "SENSITIVE"},
        "extra_allowed_types": set(),
    },
    "PCI_DSS": {
        "allowed_categories": set(),  # Triggered strictly on cardholder data
        "extra_allowed_types": PCI_CARDHOLDER_TYPES,
    },
    "PIPEDA": {
        "allowed_categories": {"PII", "PHI", "FINANCIAL", "SENSITIVE"},
        "extra_allowed_types": set(),
    },
    "GLBA": {
        "allowed_categories": {"FINANCIAL"},
        "extra_allowed_types": GLBA_FINANCIAL_TYPES,
    },
}


def map_column_to_frameworks(
    display_classification: Any,
    sensitive_data_type: Any,
    is_sensitive: bool,
    selected_frameworks: list[str] | None = None,
) -> list[str]:
    """Determines which frameworks apply to a column using Enum-safe extraction."""
    # Extract clean string values whether they are Enums, strings, or None
    raw_cat = getattr(display_classification, "value", display_classification)
    raw_type = getattr(sensitive_data_type, "value", sensitive_data_type)

    category = str(raw_cat).split(".")[-1].upper().strip() if raw_cat is not None else "PUBLIC"
    data_type = str(raw_type).split(".")[-1].upper().strip() if raw_type is not None else "NONE"

    # Discard non-sensitive and public fields immediately
    if not is_sensitive or category == "PUBLIC" or data_type == "NONE":
        return []

    active_frameworks = (
        [fw.upper() for fw in selected_frameworks]
        if selected_frameworks
        else list(FRAMEWORK_SCOPES.keys())
    )

    matched: list[str] = []
    for fw in active_frameworks:
        rule = FRAMEWORK_SCOPES.get(fw)
        if not rule:
            continue

        # Check Category Match or Specific Data Type Match
        category_match = category in rule["allowed_categories"]
        type_match = data_type in rule["extra_allowed_types"]

        # CCPA statutorily carves out HIPAA-governed PHI
        if fw == "CCPA" and category == "PHI":
            continue

        if category_match or type_match:
            matched.append(fw)

    return matched


def filter_columns_for_framework(
    framework_code: str,
    classified_columns: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Filters only the columns in scope for a given framework."""
    fw = framework_code.upper().strip()
    in_scope: list[dict[str, Any]] = []

    for col in classified_columns:
        matched = map_column_to_frameworks(
            display_classification=col.get("display_classification", "PUBLIC"),
            sensitive_data_type=col.get("sensitive_data_type", "NONE"),
            is_sensitive=col.get("is_sensitive", False),
            selected_frameworks=[fw],
        )
        if fw in matched:
            in_scope.append(col)

    return in_scope