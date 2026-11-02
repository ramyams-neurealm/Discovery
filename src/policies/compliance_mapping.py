from __future__ import annotations

from typing import Any

# Statutory category boundaries based directly on display_classification
FRAMEWORK_SCOPES: dict[str, set[str]] = {
    "HIPAA": {"PHI"},
    "GDPR": {"PII", "PHI", "FINANCIAL", "SENSITIVE"},
    "DPDP": {"PII", "PHI", "FINANCIAL", "SENSITIVE"},
    "CCPA": {"PII", "FINANCIAL", "SENSITIVE"},
    "PCI_DSS": {"FINANCIAL"},
    "PIPEDA": {"PII", "PHI", "FINANCIAL", "SENSITIVE"},
    "GLBA": {"FINANCIAL"},
}


def map_column_to_frameworks(
    display_classification: Any,
    is_sensitive: bool = True,
    selected_frameworks: list[str] | None = None,
    sensitive_data_type: Any = None,  # Kept as optional for backward compatibility
) -> list[str]:
    """Determines which frameworks apply using display_classification."""
    raw_cat = getattr(display_classification, "value", display_classification)
    category = str(raw_cat).split(".")[-1].upper().strip() if raw_cat is not None else "PUBLIC"

    if not is_sensitive or category == "PUBLIC":
        return []

    active_frameworks = (
        [fw.upper() for fw in selected_frameworks]
        if selected_frameworks
        else list(FRAMEWORK_SCOPES.keys())
    )

    matched: list[str] = []
    for fw in active_frameworks:
        allowed_categories = FRAMEWORK_SCOPES.get(fw, set())

        # CCPA statutorily carves out HIPAA-governed PHI
        if fw == "CCPA" and category == "PHI":
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
        )
        if fw in matched:
            in_scope.append(col)

    return in_scope