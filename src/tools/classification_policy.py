from __future__ import annotations

from typing import Any
from src.models.enums import DisplayClassification

REFERENCE_TABLES = {"diagnosiscodes", "procedurecodes", "pharmacyformularies", "plantypes"}


def _key(value: str) -> str:
    return "".join(ch for ch in value.lower() if ch.isalnum())


def _set(result, display, data_type: str, reason: str) -> None:
    result.display_classification = display
    result.sensitive_data_type = data_type
    result.is_sensitive = display != DisplayClassification.PUBLIC
    result.sensitivity_level = "RESTRICTED" if result.is_sensitive else "PUBLIC"
    result.reason = reason


def normalize_classification(result, payload: dict[str, Any], confidence_threshold: float):
    table = _key(payload["table_name"])
    column = _key(payload["column_name"])

    if column in {"ssn", "socialsecuritynumber"}:
        _set(result, DisplayClassification.PII, "SOCIAL_SECURITY_NUMBER", "Explicit Social Security number field.")
    elif column == "firstname":
        _set(result, DisplayClassification.PII, "FIRST_NAME", "Person first-name field.")
    elif column in {"lastname", "surname"}:
        _set(result, DisplayClassification.PII, "LAST_NAME", "Person last-name field.")
    elif column == "fullname":
        _set(result, DisplayClassification.PII, "FULL_NAME", "Person full-name field.")
    elif column in {"dateofbirth", "dob"}:
        _set(result, DisplayClassification.PII, "DATE_OF_BIRTH", "Person date-of-birth field.")
    elif column == "memberid":
        _set(result, DisplayClassification.PII, "MEMBER_IDENTIFIER", "Member identifier normalized consistently across linked tables.")
    elif column in {"npi", "providerid"}:
        _set(result, DisplayClassification.SENSITIVE, "PROVIDER_IDENTIFIER", "Provider identifier, not patient PHI by itself.")
    elif table in REFERENCE_TABLES and column in {"icdcode", "code", "procedureid", "diagnosisid", "description", "ndccode"}:
        kind = "DIAGNOSIS_CODE" if table == "diagnosiscodes" else "PROCEDURE_CODE"
        _set(result, DisplayClassification.PUBLIC, kind, "Standalone healthcare reference-catalog value, not person-linked PHI by itself.")
    elif column in {"claimid", "claimnumber", "rxclaimid"}:
        _set(result, DisplayClassification.PHI, "CLAIM_IDENTIFIER", "Healthcare claim identifier.")
    elif column in {"dateofservice", "requestdate"} and table in {"claims", "priorauthorizations"}:
        _set(result, DisplayClassification.PHI, "SERVICE_DATE", "Date linked to an identifiable healthcare event.")
    elif column in {"amount", "amountapplied", "billedamount", "paidamount", "totalpaidamount", "totalpremium", "ingredientcost"}:
        _set(result, DisplayClassification.FINANCIAL, "FINANCIAL_AMOUNT", "Monetary amount.")
    elif column == "paymentstatus":
        _set(result, DisplayClassification.FINANCIAL, "PAYMENT_STATUS", "Payment-status field.")

    if result.confidence < confidence_threshold:
        result.needs_human_review = True
        result.review_reason = result.review_reason or "Confidence below threshold."
    return result


def reconcile_linked_identifiers(results, objects):
    by_key = {(r.schema_name, r.table_name, r.column_name): r for r in results}
    for obj in objects:
        for fk in obj.get("foreign_keys", []):
            source = by_key.get((fk["source_schema"], fk["source_table"], fk["source_column"]))
            target = by_key.get((fk["target_schema"], fk["target_table"], fk["target_column"]))
            if not source or not target or source.display_classification == target.display_classification:
                continue
            chosen = source if source.display_classification != DisplayClassification.PUBLIC else target
            changed = target if chosen is source else source
            changed.display_classification = chosen.display_classification
            changed.sensitive_data_type = chosen.sensitive_data_type
            changed.is_sensitive = chosen.is_sensitive
            changed.sensitivity_level = chosen.sensitivity_level
            changed.needs_human_review = True
            changed.review_reason = "Reconciled with a linked PK/FK identifier; human validation required."
    return results


def build_classification_summary(objects, profiles, results):
    discovered = sum(len(obj.get("columns", [])) for obj in objects)
    eligible = len(profiles)
    excluded = max(discovered - eligible, 0)
    return {
        "discovered_columns": discovered,
        "eligible_columns": eligible,
        "classified_columns": len(results),
        "excluded_columns": excluded,
        "exclusion_reasons": {"NO_ELIGIBLE_TABLE_PROFILE": excluded},
    }
