from __future__ import annotations

from typing import Any

# Statutory category boundaries based directly on display_classification
FRAMEWORK_SCOPES: dict[str, set[str]] = {
    "HIPAA": {"PHI"},
    "GDPR": {"PII", "PHI", "FINANCIAL", "SENSITIVE"},
    "DPDP": {"PII", "PHI", "FINANCIAL", "SENSITIVE"},
    "CCPA": {"PII", "FINANCIAL", "SENSITIVE"},
    "CCPA_CPRA": {"PII", "FINANCIAL", "SENSITIVE"},
    "PCI_DSS": {"FINANCIAL"},
    "PIPEDA": {"PII", "PHI", "FINANCIAL", "SENSITIVE"},
    "GLBA": {"FINANCIAL"},
}

# PCI-DSS strictly applies to Cardholder Data (CHD) and Sensitive Authentication Data (SAD)
PCI_DSS_CARDHOLDER_DATA_TYPES: set[str] = {
    "CREDIT_CARD",
    "CREDIT_CARD_NUMBER",
    "PAN",
    "PRIMARY_ACCOUNT_NUMBER",
    "CVV",
    "CVC",
    "CID",
    "CARD_EXPIRATION",
    "EXPIRATION_DATE",
    "MAGNETIC_STRIPE",
    "PIN",
    "PIN_BLOCK",
}


def map_column_to_frameworks(
    display_classification: Any,
    is_sensitive: bool = True,
    selected_frameworks: list[str] | None = None,
    sensitive_data_type: Any = None,
) -> list[str]:
    """Determines which frameworks apply using display_classification and sensitive_data_type."""
    raw_cat = getattr(display_classification, "value", display_classification)
    category = str(raw_cat).split(".")[-1].upper().strip() if raw_cat is not None else "PUBLIC"

    if not is_sensitive or category == "PUBLIC":
        return []

    active_frameworks = (
        [fw.upper() for fw in selected_frameworks]
        if selected_frameworks
        else list(FRAMEWORK_SCOPES.keys())
    )

    # Extract sensitive data type if present
    raw_subtype = getattr(sensitive_data_type, "value", sensitive_data_type)
    subtype = str(raw_subtype).split(".")[-1].upper().strip() if raw_subtype is not None else ""

    matched: list[str] = []
    for fw in active_frameworks:
        # Normalize alias for lookup
        canonical_fw = "CCPA_CPRA" if fw in ("CCPA", "CCPA_CPRA") else fw
        allowed_categories = FRAMEWORK_SCOPES.get(canonical_fw, FRAMEWORK_SCOPES.get(fw, set()))

        # CCPA/CPRA statutorily carves out HIPAA-governed PHI
        if fw in ("CCPA", "CCPA_CPRA") and category == "PHI":
            continue

        # PCI-DSS scope check: must be explicitly identified cardholder/auth data
        if fw == "PCI_DSS":
            if category == "FINANCIAL" and subtype in PCI_DSS_CARDHOLDER_DATA_TYPES:
                matched.append(fw)
            continue

        if category in allowed_categories:
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
            is_sensitive=col.get("is_sensitive", False),
            selected_frameworks=[fw],
            sensitive_data_type=col.get("sensitive_data_type"),
        )
        if fw in matched:
            in_scope.append(col)

    return in_scope