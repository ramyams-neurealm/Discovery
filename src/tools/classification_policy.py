from __future__ import annotations

from typing import Any

from src.models.enums import DisplayClassification


# Reference/catalog tables contain standardized business or healthcare values.
# A value in one of these tables is not person-linked merely because a
# transactional table references it.
REFERENCE_TABLES = {
    "diagnosiscodes",
    "procedurecodes",
    "pharmacyformularies",
    "plantypes",
    "healthplans",
    "facilities",
    "providernetworks",
}

# A procedure identifier becomes PHI when its row is linked to a member,
# claim, authorization, encounter, or another identifiable healthcare event.
PERSON_LINKED_PROCEDURE_TABLES = {
    "claimlines",
    "priorauthorizations",
}

# NONE is valid only for PUBLIC output. These types provide a deterministic
# fallback for non-public results that the model returned with NONE.
GENERIC_TYPE_BY_CLASSIFICATION = {
    DisplayClassification.PII: "PERSON_IDENTIFIER",
    DisplayClassification.PHI: "HEALTH_INFORMATION",
    DisplayClassification.FINANCIAL: "FINANCIAL_INFORMATION",
    DisplayClassification.SENSITIVE: "FREE_TEXT_SENSITIVE",
}


def _key(value: str | None) -> str:
    """Return a case-insensitive alphanumeric comparison key."""
    if not value:
        return ""
    return "".join(character for character in value.lower() if character.isalnum())


def _set(
    result: Any,
    display: DisplayClassification,
    data_type: str,
    reason: str,
    *,
    require_review: bool = False,
    review_reason: str | None = None,
) -> None:
    """Apply one internally consistent classification result."""
    result.display_classification = display
    result.sensitive_data_type = data_type
    result.is_sensitive = display != DisplayClassification.PUBLIC
    result.sensitivity_level = (
        "RESTRICTED" if result.is_sensitive else "PUBLIC"
    )
    result.reason = reason

    if require_review:
        result.needs_human_review = True
        result.review_reason = (
            review_reason
            or "The deterministic policy changed an ambiguous model result."
        )


def _normalize_known_column(
    result: Any,
    table: str,
    column: str,
) -> bool:
    """
    Normalize known identifiers and sensitive fields.

    Return True when a deterministic rule was applied.
    """
    # Direct personal identifiers.
    if column in {"ssn", "socialsecuritynumber"}:
        _set(
            result,
            DisplayClassification.PII,
            "SOCIAL_SECURITY_NUMBER",
            "The column is an explicit Social Security number field.",
        )
        return True

    if column == "firstname":
        _set(
            result,
            DisplayClassification.PII,
            "FIRST_NAME",
            "The column contains a person's first name.",
        )
        return True

    if column in {"lastname", "surname"}:
        _set(
            result,
            DisplayClassification.PII,
            "LAST_NAME",
            "The column contains a person's last name.",
        )
        return True

    if column == "fullname":
        _set(
            result,
            DisplayClassification.PII,
            "FULL_NAME",
            "The column contains a person's full name.",
        )
        return True

    if column in {"dateofbirth", "dob"}:
        _set(
            result,
            DisplayClassification.PII,
            "DATE_OF_BIRTH",
            "The column contains a person's date of birth.",
        )
        return True

    if column == "memberid":
        _set(
            result,
            DisplayClassification.PII,
            "MEMBER_IDENTIFIER",
            "The column identifies a member and is normalized consistently across linked tables.",
        )
        return True

    # Healthcare claims and authorization identifiers.
    if column == "claimlineid":
        _set(
            result,
            DisplayClassification.PHI,
            "CLAIM_LINE_IDENTIFIER",
            "The column identifies a line within an identifiable healthcare claim.",
        )
        return True

    if column in {"claimid", "claimnumber", "rxclaimid"}:
        _set(
            result,
            DisplayClassification.PHI,
            "CLAIM_IDENTIFIER",
            "The column identifies a healthcare claim.",
        )
        return True

    if column == "authid":
        _set(
            result,
            DisplayClassification.SENSITIVE,
            "AUTHORIZATION_IDENTIFIER",
            "The column identifies a prior-authorization record.",
        )
        return True

    if column == "caseid":
        _set(
            result,
            DisplayClassification.SENSITIVE,
            "CASE_IDENTIFIER",
            "The column identifies an appeals or grievances case.",
        )
        return True

    # Financial identifiers and values.
    if column in {"paymentid", "claimpaymentid"}:
        _set(
            result,
            DisplayClassification.FINANCIAL,
            "PAYMENT_IDENTIFIER",
            "The column identifies a financial payment record.",
        )
        return True

    if column == "invoiceid":
        _set(
            result,
            DisplayClassification.FINANCIAL,
            "INVOICE_IDENTIFIER",
            "The column identifies a billing invoice.",
        )
        return True

    if column in {
        "amount",
        "amountapplied",
        "billedamount",
        "paidamount",
        "totalpaidamount",
        "totalpremium",
        "ingredientcost",
    }:
        _set(
            result,
            DisplayClassification.FINANCIAL,
            "FINANCIAL_AMOUNT",
            "The column contains a monetary amount.",
        )
        return True

    if column == "paymentstatus":
        _set(
            result,
            DisplayClassification.FINANCIAL,
            "PAYMENT_STATUS",
            "The column contains payment-status information.",
        )
        return True

    # Provider, organization, policy, and catalog identifiers.
    if column in {"npi", "providerid"}:
        _set(
            result,
            DisplayClassification.SENSITIVE,
            "PROVIDER_IDENTIFIER",
            "The column identifies a healthcare provider, not a patient, and is not PHI by itself.",
        )
        return True

    if column == "licenseNumber".lower():
        _set(
            result,
            DisplayClassification.SENSITIVE,
            "LICENSE_NUMBER",
            "The column contains a professional license number.",
        )
        return True

    if column == "taxid":
        _set(
            result,
            DisplayClassification.SENSITIVE,
            "TAX_IDENTIFIER",
            "The column contains a tax identifier.",
        )
        return True

    if column == "brokerid":
        _set(
            result,
            DisplayClassification.SENSITIVE,
            "BROKER_IDENTIFIER",
            "The column identifies a broker record.",
        )
        return True

    if column == "groupid":
        _set(
            result,
            DisplayClassification.SENSITIVE,
            "GROUP_IDENTIFIER",
            "The column identifies an employer or policy group.",
        )
        return True

    if column == "policyid":
        _set(
            result,
            DisplayClassification.SENSITIVE,
            "POLICY_IDENTIFIER",
            "The column identifies a member policy.",
        )
        return True

    if column == "planid":
        _set(
            result,
            DisplayClassification.PUBLIC,
            "PLAN_IDENTIFIER",
            "The column identifies a health-plan catalog record and is not person-linked by itself.",
        )
        return True

    if column == "plantypeid":
        _set(
            result,
            DisplayClassification.PUBLIC,
            "PLAN_TYPE_IDENTIFIER",
            "The column identifies a plan-type catalog record.",
        )
        return True

    if column == "facilityid":
        _set(
            result,
            DisplayClassification.PUBLIC,
            "FACILITY_IDENTIFIER",
            "The column identifies a healthcare facility.",
        )
        return True

    if column == "networkid":
        _set(
            result,
            DisplayClassification.PUBLIC,
            "NETWORK_IDENTIFIER",
            "The column identifies a provider-network record.",
        )
        return True

    # Healthcare reference data versus person-linked transaction data.
    if column == "procedureid":
        if table in PERSON_LINKED_PROCEDURE_TABLES:
            _set(
                result,
                DisplayClassification.PHI,
                "PROCEDURE_CODE",
                "The procedure identifier occurs in a member, claim, or authorization context and is person-linked health information.",
            )
        else:
            _set(
                result,
                DisplayClassification.PUBLIC,
                "PROCEDURE_CODE",
                "The procedure identifier belongs to reference data and is not person-linked PHI by itself.",
            )
        return True

    if column in {"diagnosisid", "icdcode"} and table == "diagnosiscodes":
        _set(
            result,
            DisplayClassification.PUBLIC,
            "DIAGNOSIS_CODE",
            "The value belongs to a standalone diagnosis reference catalog and is not person-linked PHI by itself.",
        )
        return True

    if column == "code" and table == "procedurecodes":
        _set(
            result,
            DisplayClassification.PUBLIC,
            "PROCEDURE_CODE",
            "The value belongs to a standalone procedure reference catalog and is not person-linked PHI by itself.",
        )
        return True

    if column == "ndccode":
        _set(
            result,
            DisplayClassification.PUBLIC,
            "DRUG_CODE",
            "The column contains a standardized drug code and is not person-linked by itself.",
        )
        return True

    # Context-aware dates and free text.
    if column == "dateofservice" and table == "claims":
        _set(
            result,
            DisplayClassification.PHI,
            "SERVICE_DATE",
            "The date is linked to an identifiable healthcare service.",
        )
        return True

    if column == "requestdate" and table == "priorauthorizations":
        _set(
            result,
            DisplayClassification.PHI,
            "SERVICE_DATE",
            "The request date is linked to an identifiable healthcare authorization.",
        )
        return True

    if column in {"effectivedate", "terminationdate"} and table == "memberpolicies":
        _set(
            result,
            DisplayClassification.SENSITIVE,
            "POLICY_DATE",
            "The date is linked to an identifiable member policy.",
        )
        return True

    if column == "resolutiondate" and table == "appealsgrievances":
        _set(
            result,
            DisplayClassification.SENSITIVE,
            "CASE_DATE",
            "The date is linked to an appeals or grievances case.",
        )
        return True

    if column == "description":
        if table == "diagnosiscodes":
            _set(
                result,
                DisplayClassification.PUBLIC,
                "DIAGNOSIS_CODE",
                "The description belongs to a diagnosis reference catalog.",
            )
        elif table == "procedurecodes":
            _set(
                result,
                DisplayClassification.PUBLIC,
                "PROCEDURE_CODE",
                "The description belongs to a procedure reference catalog.",
            )
        elif table in {"plantypes", "pharmacyformularies"}:
            _set(
                result,
                DisplayClassification.PUBLIC,
                "NONE",
                "The description belongs to a public reference catalog.",
            )
        elif table == "appealsgrievances":
            _set(
                result,
                DisplayClassification.SENSITIVE,
                "FREE_TEXT_SENSITIVE",
                "Free text in an appeals or grievances case may contain sensitive details.",
                require_review=True,
                review_reason="Free-text content requires human validation.",
            )
        return True

    return False


def _enforce_type_consistency(result: Any) -> None:
    """Ensure NONE is used only with PUBLIC output."""
    raw_type = getattr(result.sensitive_data_type, "value", result.sensitive_data_type)
    normalized_type = str(raw_type or "").strip().upper()

    if result.display_classification == DisplayClassification.PUBLIC:
        if not normalized_type:
            result.sensitive_data_type = "NONE"
        result.is_sensitive = False
        result.sensitivity_level = "PUBLIC"
        return

    result.is_sensitive = True
    result.sensitivity_level = "RESTRICTED"

    if normalized_type in {"", "NONE"}:
        result.sensitive_data_type = GENERIC_TYPE_BY_CLASSIFICATION[
            result.display_classification
        ]
        result.needs_human_review = True
        result.review_reason = (
            result.review_reason
            or "A non-public classification required a specific sensitive data type."
        )


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
        result.review_reason = (
            result.review_reason
            or "Confidence below the configured classification threshold."
        )

    result.inference_basis = list(
        dict.fromkeys(getattr(result, "inference_basis", []) or [])
    )
    return result


def reconcile_linked_identifiers(results: list[Any], objects: list[dict[str, Any]]):
    """
    Reapply canonical rules to both FK endpoints without copying classifications.

    Reference-side and transaction-side columns may intentionally differ. For
    example, ProcedureCodes.ProcedureID is PUBLIC reference data, while
    ClaimLines.ProcedureID is PHI because it is linked to a healthcare claim.
    """
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
