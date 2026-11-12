from __future__ import annotations

from typing import Any

from src.models.enums import DisplayClassification

# Standalone reference catalogs
REFERENCE_TABLES = {
    "diagnosiscodes",
    "procedurecodes",
    "pharmacyformularies",
    "plantypes",
    "healthplans",
    "facilities",
    "providernetworks",
}

# Transactional tables where medical procedures link to an identifiable person
PERSON_LINKED_PROCEDURE_TABLES = {
    "claimlines",
    "priorauthorizations",
}


def _key(value: str | None) -> str:
    """Return a case-insensitive alphanumeric comparison key."""
    if not value:
        return ""
    return "".join(character for character in value.lower() if character.isalnum())


def _normalize_subtype(raw_subtype: Any) -> str | None:
    """Canonicalize sensitive_data_type strings and filter empty/NONE tokens."""
    if raw_subtype is None:
        return None
    if hasattr(raw_subtype, "value"):
        raw_subtype = raw_subtype.value
    cleaned = str(raw_subtype).strip().upper().replace("-", "_").replace(" ", "_")
    if cleaned in {"", "NONE", "NULL", "N/A", "NA", "UNKNOWN", "GENERIC"}:
        return None
    aliases = {
        "PAN": "CREDIT_CARD_NUMBER",
        "PRIMARY_ACCOUNT_NUMBER": "CREDIT_CARD_NUMBER",
        "CREDIT_CARD": "CREDIT_CARD_NUMBER",
        "CARD_NUMBER": "CREDIT_CARD_NUMBER",
        "CVC": "CVV",
        "CID": "CVV",
        "EXPIRATION_DATE": "CARD_EXPIRATION",
        "EXPIRY_DATE": "CARD_EXPIRATION",
        "CARD_EXPIRY": "CARD_EXPIRATION",
        "PIN": "PIN_BLOCK",
        "SOCIAL_SECURITY_NUMBER": "SSN",
        "ACCOUNT_NUMBER": "BANK_ACCOUNT_NUMBER",
        "DOB": "DATE_OF_BIRTH",
        "EMAIL": "EMAIL_ADDRESS",
        "PHONE": "PHONE_NUMBER",
    }
    return aliases.get(cleaned, cleaned)


def _set(
    result: Any,
    display: DisplayClassification,
    *,
    subtype: str | None = None,
    require_review: bool = False,
) -> None:
    """Apply one internally consistent classification result."""
    result.display_classification = display
    result.is_sensitive = display != DisplayClassification.PUBLIC
    if display == DisplayClassification.PUBLIC:
        result.sensitive_data_type = None
    elif subtype is not None:
        result.sensitive_data_type = subtype

    if require_review:
        result.needs_human_review = True


def _normalize_known_column(
    result: Any,
    table: str,
    column: str,
) -> bool:
    """Normalize known identifiers and sensitive fields."""
    # Clinical and patient summary tables (PHI)
    if column in {"allergyid", "patientid", "encounterid", "conditionid"}:
        if any(term in table for term in {"patient", "allergy", "appointment", "summary", "clinical"}):
            _set(result, DisplayClassification.PHI)
            return True

    # Payment cardholder and authentication data (PCI-DSS)
    if column in {"cardnumber", "cardnumberencrypted", "pan", "primaryaccountnumber", "creditcardnumber"}:
        _set(result, DisplayClassification.FINANCIAL, subtype="CREDIT_CARD_NUMBER")
        return True

    if column in {"cvv", "cvvencrypted", "cvc", "cvc2", "cid"}:
        _set(result, DisplayClassification.FINANCIAL, subtype="CVV")
        return True

    if column in {"expirydate", "cardexpiry", "cardexpiration", "expirationdate"}:
        _set(result, DisplayClassification.FINANCIAL, subtype="CARD_EXPIRATION")
        return True

    if column in {"cardholdername", "nameoncard"}:
        _set(result, DisplayClassification.PII, subtype="CARDHOLDER_NAME")
        return True

    if column in {"pin", "pinblock", "encryptedpin"}:
        _set(result, DisplayClassification.FINANCIAL, subtype="PIN_BLOCK")
        return True

    # Direct personal identifiers (PII)
    if column in {"ssn", "socialsecuritynumber"}:
        _set(result, DisplayClassification.PII, subtype="SSN")
        return True

    if column == "firstname":
        _set(result, DisplayClassification.PII, subtype="FIRST_NAME")
        return True

    if column in {"lastname", "surname"}:
        _set(result, DisplayClassification.PII, subtype="LAST_NAME")
        return True

    if column == "fullname":
        _set(result, DisplayClassification.PII, subtype="FULL_NAME")
        return True

    if column in {"dateofbirth", "dob"}:
        _set(result, DisplayClassification.PII, subtype="DATE_OF_BIRTH")
        return True

    if column == "memberid":
        _set(result, DisplayClassification.PII)
        return True

    # Healthcare claims and service records (PHI)
    if column in {
        "claimlineid",
        "claimid",
        "claimnumber",
        "rxclaimid",
    }:
        _set(result, DisplayClassification.PHI)
        return True

    if column == "dateofservice" and table == "claims":
        _set(result, DisplayClassification.PHI)
        return True

    if column == "requestdate" and table == "priorauthorizations":
        _set(result, DisplayClassification.PHI)
        return True

    # Sensitive administrative / operational
    if column in {"authid", "caseid"}:
        _set(result, DisplayClassification.SENSITIVE)
        return True

    if column in {
        "npi",
        "providerid",
        "taxid",
        "brokerid",
        "groupid",
        "policyid",
    } or column == "licensenumber":
        _set(result, DisplayClassification.SENSITIVE)
        return True

    if column in {"effectivedate", "terminationdate"} and table == "memberpolicies":
        _set(result, DisplayClassification.SENSITIVE)
        return True

    if column == "resolutiondate" and table == "appealsgrievances":
        _set(result, DisplayClassification.SENSITIVE)
        return True

    # Financial accounts and amounts
    if column == "accountnumber":
        _set(result, DisplayClassification.FINANCIAL, subtype="BANK_ACCOUNT_NUMBER")
        return True

    if column in {
        "accountid",
        "accounttypeid",
        "currentbalance",
        "availablebalance",
        "holdbalance",
        "minimumopeningbalance",
        "minimumdailybalance",
        "monthlymaintenancefee",
        "overdraftlimit",
        "baseinterestrate",
        "paymentid",
        "claimpaymentid",
        "invoiceid",
        "amount",
        "amountapplied",
        "billedamount",
        "paidamount",
        "totalpaidamount",
        "totalpremium",
        "ingredientcost",
        "paymentstatus",
    }:
        _set(result, DisplayClassification.FINANCIAL)
        return True

    # Reference catalogs vs transactional
    if column == "procedureid":
        if table in PERSON_LINKED_PROCEDURE_TABLES:
            _set(result, DisplayClassification.PHI)
        else:
            _set(result, DisplayClassification.PUBLIC)
        return True

    if column in {"planid", "plantypeid", "facilityid", "networkid", "ndccode"}:
        _set(result, DisplayClassification.PUBLIC)
        return True

    if column in {"diagnosisid", "icdcode"} and table == "diagnosiscodes":
        _set(result, DisplayClassification.PUBLIC)
        return True

    if column == "code" and table == "procedurecodes":
        _set(result, DisplayClassification.PUBLIC)
        return True

    # Generic description fields
    if column == "description":
        if table in {"diagnosiscodes", "procedurecodes", "plantypes", "pharmacyformularies"}:
            _set(result, DisplayClassification.PUBLIC)
            return True
        elif table == "appealsgrievances":
            _set(result, DisplayClassification.SENSITIVE, require_review=True)
            return True

    return False


def _enforce_type_consistency(result: Any) -> None:
    """Ensure is_sensitive and sensitive_data_type are aligned with display_classification."""
    result.is_sensitive = result.display_classification != DisplayClassification.PUBLIC
    if not result.is_sensitive:
        result.sensitive_data_type = None
    elif hasattr(result, "sensitive_data_type"):
        result.sensitive_data_type = _normalize_subtype(result.sensitive_data_type)


def normalize_classification(
    result: Any,
    payload: dict[str, Any],
    confidence_threshold: float,
):
    """Apply deterministic, context-aware policy after GPT classification."""
    table = _key(payload.get("table_name"))
    column = _key(payload.get("column_name"))

    _normalize_known_column(result, table, column)
    _enforce_type_consistency(result)

    if result.confidence < confidence_threshold:
        result.needs_human_review = True

    return result


def reconcile_linked_identifiers(results: list[Any], objects: list[dict[str, Any]]):
    """Reapply canonical rules to both FK endpoints."""
    by_key = {
        (result.schema_name, result.table_name, result.column_name): result
        for result in results
    }

    for database_object in objects:
        for foreign_key in database_object.get("foreign_keys", []):
            endpoint_keys = (
                (
                    foreign_key.get("source_schema"),
                    foreign_key.get("source_table"),
                    foreign_key.get("source_column"),
                ),
                (
                    foreign_key.get("target_schema"),
                    foreign_key.get("target_table"),
                    foreign_key.get("target_column"),
                ),
            )

            for endpoint_key in endpoint_keys:
                result = by_key.get(endpoint_key)
                if result is None:
                    continue

                table = _key(result.table_name)
                column = _key(result.column_name)
                _normalize_known_column(result, table, column)
                _enforce_type_consistency(result)

    return results


def build_classification_summary(
    objects: list[dict[str, Any]],
    profiles: list[dict[str, Any]],
    results: list[Any],
) -> dict[str, Any]:
    """Build an auditable summary of discovered and eligible columns."""
    discovered = sum(
        len(database_object.get("columns", []))
        for database_object in objects
    )
    eligible = len(profiles)
    excluded = max(discovered - eligible, 0)

    return {
        "discovered_columns": discovered,
        "eligible_columns": eligible,
        "classified_columns": len(results),
        "excluded_columns": excluded,
        "exclusion_reasons": {
            "NO_ELIGIBLE_TABLE_PROFILE": excluded,
        },
    }