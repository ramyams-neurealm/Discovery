# # from __future__ import annotations

# # from typing import Any

# # # Statutory category boundaries based directly on display_classification
# # FRAMEWORK_SCOPES: dict[str, set[str]] = {
# #     "HIPAA": {"PHI"},
# #     "GDPR": {"PII", "PHI", "FINANCIAL", "SENSITIVE"},
# #     "DPDP": {"PII", "PHI", "FINANCIAL", "SENSITIVE"},
# #     "CCPA": {"PII", "FINANCIAL", "SENSITIVE"},
# #     "CCPA_CPRA": {"PII", "FINANCIAL", "SENSITIVE"},
# #     "PCI_DSS": {"FINANCIAL"},
# #     "PIPEDA": {"PII", "PHI", "FINANCIAL", "SENSITIVE"},
# #     "GLBA": {"FINANCIAL"},
# # }

# # # Primary Account Number (PAN) subtypes that establish PCI-DSS Cardholder Data context
# # PCI_DSS_PAN_DATA_TYPES: set[str] = {
# #     "CREDIT_CARD",
# #     "CREDIT_CARD_NUMBER",
# #     "PAN",
# #     "PRIMARY_ACCOUNT_NUMBER",
# # }

# # # Sensitive Authentication Data (SAD) subtypes independently subject to PCI-DSS
# # PCI_DSS_SAD_DATA_TYPES: set[str] = {
# #     "CVV",
# #     "CVC",
# #     "CID",
# #     "MAGNETIC_STRIPE",
# #     "PIN",
# #     "PIN_BLOCK",
# # }

# # # Primary PCI-DSS subtypes that independently place a column in PCI-DSS scope
# # PCI_DSS_PRIMARY_DATA_TYPES: set[str] = PCI_DSS_PAN_DATA_TYPES | PCI_DSS_SAD_DATA_TYPES

# # # Secondary cardholder elements that are in PCI-DSS scope ONLY when co-located with PAN
# # PCI_DSS_CONTEXTUAL_CARDHOLDER_TYPES: set[str] = {
# #     "CARDHOLDER_NAME",
# #     "CARD_EXPIRATION",
# #     "EXPIRATION_DATE",
# # }


# # def _extract_subtype(sensitive_data_type: Any) -> str:
# #     raw_subtype = getattr(sensitive_data_type, "value", sensitive_data_type)
# #     return str(raw_subtype).split(".")[-1].upper().strip() if raw_subtype is not None else ""


# # def map_column_to_frameworks(
# #     display_classification: Any,
# #     is_sensitive: bool = True,
# #     selected_frameworks: list[str] | None = None,
# #     sensitive_data_type: Any = None,
# #     has_pan_context: bool = False,
# # ) -> list[str]:
# #     """Determines which frameworks apply using display_classification, subtype, and table context."""
# #     raw_cat = getattr(display_classification, "value", display_classification)
# #     category = str(raw_cat).split(".")[-1].upper().strip() if raw_cat is not None else "PUBLIC"

# #     if not is_sensitive or category == "PUBLIC":
# #         return []

# #     active_frameworks = (
# #         [fw.upper() for fw in selected_frameworks]
# #         if selected_frameworks
# #         else list(FRAMEWORK_SCOPES.keys())
# #     )

# #     subtype = _extract_subtype(sensitive_data_type)

# #     matched: list[str] = []
# #     for fw in active_frameworks:
# #         canonical_fw = "CCPA_CPRA" if fw in ("CCPA", "CCPA_CPRA") else fw
# #         allowed_categories = FRAMEWORK_SCOPES.get(canonical_fw, FRAMEWORK_SCOPES.get(fw, set()))

# #         # CCPA/CPRA statutorily carves out HIPAA-governed PHI
# #         if fw in ("CCPA", "CCPA_CPRA") and category == "PHI":
# #             continue

# #         # PCI-DSS scope check:
# #         # - PAN or SAD independently triggers PCI-DSS
# #         # - CARDHOLDER_NAME / CARD_EXPIRATION trigger PCI-DSS only when PAN exists in the table/context
# #         if fw == "PCI_DSS":
# #             if category == "FINANCIAL" and subtype in PCI_DSS_PRIMARY_DATA_TYPES:
# #                 matched.append(fw)
# #             elif (
# #                 has_pan_context
# #                 and category in ("FINANCIAL", "PII")
# #                 and subtype in PCI_DSS_CONTEXTUAL_CARDHOLDER_TYPES
# #             ):
# #                 matched.append(fw)
# #             continue

# #         if category in allowed_categories:
# #             matched.append(fw)

# #     return matched


# # def filter_columns_for_framework(
# #     framework_code: str,
# #     classified_columns: list[dict[str, Any]],
# # ) -> list[dict[str, Any]]:
# #     """Filters only the columns in scope for a given framework, scoped strictly per table."""
# #     fw = framework_code.upper().strip()
# #     in_scope: list[dict[str, Any]] = []

# #     # Compute PAN presence strictly per (schema_name, table_name) so PAN in one table
# #     # never leaks PCI-DSS scope into cardholder names/expirations of another table.
# #     tables_with_pan: set[tuple[str, str]] = set()
# #     for col in classified_columns:
# #         if not col.get("is_sensitive", False):
# #             continue
# #         if _extract_subtype(col.get("sensitive_data_type")) in PCI_DSS_PAN_DATA_TYPES:
# #             table_key = (
# #                 str(col.get("schema_name") or "").lower().strip(),
# #                 str(col.get("table_name") or "").lower().strip(),
# #             )
# #             tables_with_pan.add(table_key)

# #     for col in classified_columns:
# #         table_key = (
# #             str(col.get("schema_name") or "").lower().strip(),
# #             str(col.get("table_name") or "").lower().strip(),
# #         )
# #         has_pan_in_same_table = table_key in tables_with_pan

# #         matched = map_column_to_frameworks(
# #             display_classification=col.get("display_classification", "PUBLIC"),
# #             is_sensitive=col.get("is_sensitive", False),
# #             selected_frameworks=[fw],
# #             sensitive_data_type=col.get("sensitive_data_type"),
# #             has_pan_context=has_pan_in_same_table,
# #         )
# #         if fw in matched:
# #             in_scope.append(col)

# #     return in_scope
# from __future__ import annotations

# from typing import Any

# # Statutory category boundaries based directly on display_classification
# FRAMEWORK_SCOPES: dict[str, set[str]] = {
#     "HIPAA": {"PHI"},
#     "GDPR": {"PII", "PHI", "FINANCIAL", "SENSITIVE"},
#     "DPDP": {"PII", "PHI", "FINANCIAL", "SENSITIVE"},
#     "CCPA": {"PII", "FINANCIAL", "SENSITIVE"},
#     "CCPA_CPRA": {"PII", "FINANCIAL", "SENSITIVE"},
#     "PCI_DSS": {"FINANCIAL"},
#     "PIPEDA": {"PII", "PHI", "FINANCIAL", "SENSITIVE"},
#     "GLBA": {"FINANCIAL"},
# }

# # Primary Account Number (PAN) subtypes that establish PCI-DSS Cardholder Data context
# PCI_DSS_PAN_DATA_TYPES: set[str] = {
#     "CREDIT_CARD",
#     "CREDIT_CARD_NUMBER",
#     "PAN",
#     "PRIMARY_ACCOUNT_NUMBER",
# }

# # Sensitive Authentication Data (SAD) subtypes independently subject to PCI-DSS
# PCI_DSS_SAD_DATA_TYPES: set[str] = {
#     "CVV",
#     "CVC",
#     "CID",
#     "MAGNETIC_STRIPE",
#     "PIN",
#     "PIN_BLOCK",
# }

# # Primary PCI-DSS subtypes that independently place a column in PCI-DSS scope
# PCI_DSS_PRIMARY_DATA_TYPES: set[str] = PCI_DSS_PAN_DATA_TYPES | PCI_DSS_SAD_DATA_TYPES

# # Secondary cardholder elements that are in PCI-DSS scope ONLY when co-located with PAN
# PCI_DSS_CONTEXTUAL_CARDHOLDER_TYPES: set[str] = {
#     "CARDHOLDER_NAME",
#     "CARD_EXPIRATION",
#     "EXPIRATION_DATE",
# }


# def _extract_category(display_classification: Any) -> str:
#     raw_cat = getattr(display_classification, "value", display_classification)
#     return str(raw_cat).split(".")[-1].upper().strip() if raw_cat is not None else "PUBLIC"


# def _extract_subtype(sensitive_data_type: Any) -> str:
#     raw_subtype = getattr(sensitive_data_type, "value", sensitive_data_type)
#     return str(raw_subtype).split(".")[-1].upper().strip() if raw_subtype is not None else ""


# def _normalize_table_key(schema_name: Any, table_name: Any) -> tuple[str, str]:
#     return (
#         str(schema_name or "").lower().strip(),
#         str(table_name or "").lower().strip(),
#     )


# def map_column_to_frameworks(
#     display_classification: Any,
#     is_sensitive: bool = True,
#     selected_frameworks: list[str] | None = None,
#     sensitive_data_type: Any = None,
#     has_pan_context: bool = False,
#     has_phi_context: bool = False,
# ) -> list[str]:
#     """Determines which frameworks apply using display_classification, subtype, and relational table context."""
#     category = _extract_category(display_classification)

#     if not is_sensitive or category == "PUBLIC":
#         return []

#     active_frameworks = (
#         [fw.upper() for fw in selected_frameworks]
#         if selected_frameworks
#         else list(FRAMEWORK_SCOPES.keys())
#     )

#     subtype = _extract_subtype(sensitive_data_type)

#     matched: list[str] = []
#     for fw in active_frameworks:
#         canonical_fw = "CCPA_CPRA" if fw in ("CCPA", "CCPA_CPRA") else fw
#         allowed_categories = FRAMEWORK_SCOPES.get(canonical_fw, FRAMEWORK_SCOPES.get(fw, set()))

#         # CCPA/CPRA statutorily carves out HIPAA-governed PHI
#         if fw in ("CCPA", "CCPA_CPRA") and category == "PHI":
#             continue

#         # HIPAA scope check (data-driven):
#         # - Direct PHI is always in HIPAA scope
#         # - FINANCIAL columns in a table containing PHI (or linked via FK to a PHI table)
#         #   are regulated as payment-for-healthcare PHI under 45 CFR § 160.103
#         if fw == "HIPAA":
#             if category == "PHI" or (category == "FINANCIAL" and has_phi_context):
#                 matched.append(fw)
#             continue

#         # PCI-DSS scope check (data-driven):
#         # - PAN or SAD independently triggers PCI-DSS
#         # - CARDHOLDER_NAME / CARD_EXPIRATION trigger PCI-DSS only when PAN exists in the table/context
#         if fw == "PCI_DSS":
#             if category == "FINANCIAL" and subtype in PCI_DSS_PRIMARY_DATA_TYPES:
#                 matched.append(fw)
#             elif (
#                 has_pan_context
#                 and category in ("FINANCIAL", "PII")
#                 and subtype in PCI_DSS_CONTEXTUAL_CARDHOLDER_TYPES
#             ):
#                 matched.append(fw)
#             continue

#         if category in allowed_categories:
#             matched.append(fw)

#     return matched


# def filter_columns_for_framework(
#     framework_code: str,
#     classified_columns: list[dict[str, Any]],
#     dependency_edges: list[dict[str, Any]] | None = None,
# ) -> list[dict[str, Any]]:
#     """Filters columns in scope for a framework using intra-table co-location and optional FK graph edges."""
#     fw = framework_code.upper().strip()
#     in_scope: list[dict[str, Any]] = []

#     tables_with_pan: set[tuple[str, str]] = set()
#     tables_with_phi: set[tuple[str, str]] = set()

#     # Pass 1: Identify tables that empirically contain PAN or PHI columns
#     for col in classified_columns:
#         if not col.get("is_sensitive", False):
#             continue

#         table_key = _normalize_table_key(col.get("schema_name"), col.get("table_name"))

#         if _extract_subtype(col.get("sensitive_data_type")) in PCI_DSS_PAN_DATA_TYPES:
#             tables_with_pan.add(table_key)

#         if _extract_category(col.get("display_classification")) == "PHI":
#             tables_with_phi.add(table_key)

#     # Pass 2 (Optional): Propagate PHI context across foreign-key dependency edges
#     if dependency_edges and tables_with_phi:
#         phi_table_names = {tbl for _, tbl in tables_with_phi}
#         for edge in dependency_edges:
#             src = str(edge.get("source_object") or "").lower().strip()
#             tgt = str(edge.get("target_object") or "").lower().strip()
#             # Handle schema-qualified object names (e.g., "public.billing")
#             src_tbl = src.split(".")[-1]
#             tgt_tbl = tgt.split(".")[-1]

#             if tgt_tbl in phi_table_names:
#                 for col in classified_columns:
#                     if str(col.get("table_name") or "").lower().strip() == src_tbl:
#                         tables_with_phi.add(_normalize_table_key(col.get("schema_name"), src_tbl))

#     # Pass 3: Evaluate each column with its resolved table context
#     for col in classified_columns:
#         table_key = _normalize_table_key(col.get("schema_name"), col.get("table_name"))

#         matched = map_column_to_frameworks(
#             display_classification=col.get("display_classification", "PUBLIC"),
#             is_sensitive=col.get("is_sensitive", False),
#             selected_frameworks=[fw],
#             sensitive_data_type=col.get("sensitive_data_type"),
#             has_pan_context=table_key in tables_with_pan,
#             has_phi_context=table_key in tables_with_phi,
#         )
#         if fw in matched:
#             in_scope.append(col)

#     return in_scope






from __future__ import annotations

from typing import Any

# Statutory category boundaries based directly on display_classification
FRAMEWORK_SCOPES: dict[str, set[str]] = {
    "HIPAA": {"PHI"},
    "GDPR": {"PII", "PHI", "FINANCIAL", "SENSITIVE"},
    "DPDP": {"PII", "PHI", "FINANCIAL", "SENSITIVE"},
    "CCPA": {"PII", "PHI", "FINANCIAL", "SENSITIVE"},
    "CCPA_CPRA": {"PII", "PHI", "FINANCIAL", "SENSITIVE"},
    "PCI_DSS": {"FINANCIAL"},
    "PIPEDA": {"PII", "PHI", "FINANCIAL", "SENSITIVE"},
    "GLBA": {"FINANCIAL"},
}

# Primary Account Number (PAN) subtypes that establish PCI-DSS Cardholder Data context
PCI_DSS_PAN_DATA_TYPES: set[str] = {
    "CREDIT_CARD",
    "CREDIT_CARD_NUMBER",
    "PAN",
    "PRIMARY_ACCOUNT_NUMBER",
}

# Sensitive Authentication Data (SAD) subtypes independently subject to PCI-DSS
PCI_DSS_SAD_DATA_TYPES: set[str] = {
    "CVV",
    "CVC",
    "CID",
    "MAGNETIC_STRIPE",
    "PIN",
    "PIN_BLOCK",
}

# Primary PCI-DSS subtypes that independently place a column in PCI-DSS scope
PCI_DSS_PRIMARY_DATA_TYPES: set[str] = PCI_DSS_PAN_DATA_TYPES | PCI_DSS_SAD_DATA_TYPES

# Secondary cardholder elements that are in PCI-DSS scope ONLY when co-located with PAN
PCI_DSS_CONTEXTUAL_CARDHOLDER_TYPES: set[str] = {
    "CARDHOLDER_NAME",
    "CARD_EXPIRATION",
    "EXPIRATION_DATE",
}


def _extract_category(display_classification: Any) -> str:
    raw_cat = getattr(display_classification, "value", display_classification)
    return str(raw_cat).split(".")[-1].upper().strip() if raw_cat is not None else "PUBLIC"


def _extract_subtype(sensitive_data_type: Any) -> str:
    raw_subtype = getattr(sensitive_data_type, "value", sensitive_data_type)
    return str(raw_subtype).split(".")[-1].upper().strip() if raw_subtype is not None else ""


def _normalize_table_key(schema_name: Any, table_name: Any) -> tuple[str, str]:
    return (
        str(schema_name or "").lower().strip(),
        str(table_name or "").lower().strip(),
    )


def _get_edge_field(edge: Any, field_name: str) -> str:
    val = edge.get(field_name) if isinstance(edge, dict) else getattr(edge, field_name, None)
    return str(val or "").lower().strip()


def map_column_to_frameworks(
    display_classification: Any,
    is_sensitive: bool = True,
    selected_frameworks: list[str] | None = None,
    sensitive_data_type: Any = None,
    has_pan_context: bool = False,
    has_phi_context: bool = False,
) -> list[str]:
    """Determines which frameworks apply using display_classification, subtype, and relational table context."""
    category = _extract_category(display_classification)

    if not is_sensitive or category == "PUBLIC":
        return []

    active_frameworks = (
        [fw.upper() for fw in selected_frameworks]
        if selected_frameworks
        else list(FRAMEWORK_SCOPES.keys())
    )

    subtype = _extract_subtype(sensitive_data_type)

    matched: list[str] = []
    for fw in active_frameworks:
        canonical_fw = "CCPA_CPRA" if fw in ("CCPA", "CCPA_CPRA") else fw
        allowed_categories = FRAMEWORK_SCOPES.get(canonical_fw, FRAMEWORK_SCOPES.get(fw, set()))

        # CCPA/CPRA statutorily carves out HIPAA-governed PHI
        if fw in ("CCPA", "CCPA_CPRA") and category == "PHI":
            continue

        # HIPAA scope check (data-driven):
        # - Direct PHI is always in HIPAA scope
        # - FINANCIAL columns in a table containing PHI (or linked via FK to a PHI table)
        #   are regulated as payment-for-healthcare PHI under 45 CFR § 160.103
        if fw == "HIPAA":
            if category == "PHI" or (category == "FINANCIAL" and has_phi_context):
                matched.append(fw)
            continue

        # PCI-DSS scope check (data-driven):
        # - PAN or SAD independently triggers PCI-DSS
        # - CARDHOLDER_NAME / CARD_EXPIRATION trigger PCI-DSS only when PAN exists in the table/context
        if fw == "PCI_DSS":
            if category == "FINANCIAL" and subtype in PCI_DSS_PRIMARY_DATA_TYPES:
                matched.append(fw)
            elif (
                has_pan_context
                and category in ("FINANCIAL", "PII")
                and subtype in PCI_DSS_CONTEXTUAL_CARDHOLDER_TYPES
            ):
                matched.append(fw)
            continue

        if category in allowed_categories:
            matched.append(fw)

    return matched


def filter_columns_for_framework(
    framework_code: str,
    classified_columns: list[dict[str, Any]],
    dependency_edges: list[Any] | None = None,
) -> list[dict[str, Any]]:
    """Filters columns in scope for a framework using intra-table co-location and optional FK graph edges."""
    fw = framework_code.upper().strip()
    in_scope: list[dict[str, Any]] = []

    tables_with_pan: set[tuple[str, str]] = set()
    tables_with_phi: set[tuple[str, str]] = set()

    # Pass 1: Identify tables that empirically contain PAN or PHI columns
    for col in classified_columns:
        if not col.get("is_sensitive", False):
            continue

        table_key = _normalize_table_key(col.get("schema_name"), col.get("table_name"))

        if _extract_subtype(col.get("sensitive_data_type")) in PCI_DSS_PAN_DATA_TYPES:
            tables_with_pan.add(table_key)

        if _extract_category(col.get("display_classification")) == "PHI":
            tables_with_phi.add(table_key)

    # Pass 2 (Optional): Propagate PHI context across foreign-key dependency edges
    if dependency_edges and tables_with_phi:
        phi_table_names = {tbl for _, tbl in tables_with_phi}
        for edge in dependency_edges:
            src = _get_edge_field(edge, "source_object")
            tgt = _get_edge_field(edge, "target_object")
            # Handle schema-qualified object names (e.g., "public.billing")
            src_tbl = src.split(".")[-1]
            tgt_tbl = tgt.split(".")[-1]

            if tgt_tbl in phi_table_names:
                for col in classified_columns:
                    if str(col.get("table_name") or "").lower().strip() == src_tbl:
                        tables_with_phi.add(_normalize_table_key(col.get("schema_name"), src_tbl))

    # Pass 3: Evaluate each column with its resolved table context
    for col in classified_columns:
        table_key = _normalize_table_key(col.get("schema_name"), col.get("table_name"))

        matched = map_column_to_frameworks(
            display_classification=col.get("display_classification", "PUBLIC"),
            is_sensitive=col.get("is_sensitive", False),
            selected_frameworks=[fw],
            sensitive_data_type=col.get("sensitive_data_type"),
            has_pan_context=table_key in tables_with_pan,
            has_phi_context=table_key in tables_with_phi,
        )
        if fw in matched:
            in_scope.append(col)

    return in_scope
