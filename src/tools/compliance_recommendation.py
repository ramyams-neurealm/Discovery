from __future__ import annotations

from collections import defaultdict
from typing import Any

RECOMMENDATION_POLICY_VERSION = "framework-recommendation-v1.1"

APPROVED_SENSITIVE_DATA_TYPES = {
    "NONE", "PERSON_IDENTIFIER", "FIRST_NAME", "LAST_NAME", "FULL_NAME",
    "EMAIL_ADDRESS", "PHONE_NUMBER", "DATE_OF_BIRTH", "PHYSICAL_ADDRESS",
    "IP_ADDRESS", "PASSPORT_NUMBER", "DRIVER_LICENSE_NUMBER",
    "SOCIAL_SECURITY_NUMBER", "US_TAX_IDENTIFIER", "IN_PAN", "IN_AADHAAR",
    "IN_VOTER_ID", "CANADIAN_SIN", "MEMBER_IDENTIFIER",
    "MEDICAL_RECORD_NUMBER", "HEALTH_INSURANCE_NUMBER", "HEALTH_INFORMATION",
    "DIAGNOSIS_INFORMATION", "DIAGNOSIS_CODE", "PROCEDURE_CODE",
    "SERVICE_DATE", "PRESCRIPTION_INFORMATION", "CLAIM_IDENTIFIER",
    "CLAIM_LINE_IDENTIFIER", "AUTHORIZATION_IDENTIFIER", "CASE_IDENTIFIER",
    "PROVIDER_IDENTIFIER", "LICENSE_NUMBER", "TAX_IDENTIFIER",
    "BROKER_IDENTIFIER", "GROUP_IDENTIFIER", "POLICY_IDENTIFIER",
    "PLAN_IDENTIFIER", "PLAN_TYPE_IDENTIFIER", "FACILITY_IDENTIFIER",
    "NETWORK_IDENTIFIER", "DRUG_CODE", "POLICY_DATE", "CASE_DATE",
    "CREDIT_CARD_NUMBER", "BANK_ACCOUNT_NUMBER", "IBAN",
    "FINANCIAL_INFORMATION", "FINANCIAL_AMOUNT", "PAYMENT_IDENTIFIER",
    "PAYMENT_STATUS", "INVOICE_IDENTIFIER", "LOGIN_CREDENTIAL",
    "BIOMETRIC_DATA", "FREE_TEXT_SENSITIVE",
}

TYPE_ALIASES = {
    "EMAIL": "EMAIL_ADDRESS", "EMAIL_ID": "EMAIL_ADDRESS",
    "CUSTOMER_EMAIL": "EMAIL_ADDRESS", "PHONE": "PHONE_NUMBER",
    "MOBILE_NUMBER": "PHONE_NUMBER", "DOB": "DATE_OF_BIRTH",
    "SSN": "SOCIAL_SECURITY_NUMBER", "US_SSN": "SOCIAL_SECURITY_NUMBER",
    "PAN": "IN_PAN", "AADHAAR": "IN_AADHAAR",
    "CREDIT_CARD": "CREDIT_CARD_NUMBER", "CARD_NUMBER": "CREDIT_CARD_NUMBER",
    "BANK_NUMBER": "BANK_ACCOUNT_NUMBER", "ACCOUNT_NUMBER": "BANK_ACCOUNT_NUMBER",
    "BANK_ACCOUNT": "BANK_ACCOUNT_NUMBER",
    "ACCOUNT_IDENTIFIER": "FINANCIAL_INFORMATION",
    "ACCOUNT_INFORMATION": "FINANCIAL_INFORMATION",
    "ACCOUNT_STATUS": "FINANCIAL_INFORMATION",
    "ACCOUNT_TYPE_IDENTIFIER": "FINANCIAL_INFORMATION",
    "ACCOUNT_FEATURE": "FINANCIAL_INFORMATION",
    "FINANCIAL_DATA": "FINANCIAL_INFORMATION",
    "FINANCIAL_REFERENCE": "FINANCIAL_INFORMATION",
    "FINANCIAL_DATE": "FINANCIAL_INFORMATION",
    "FINANCIAL_DATE/TIME": "FINANCIAL_INFORMATION",
    "FINANCIAL_DATE_TIME": "FINANCIAL_INFORMATION",
    "FINANCIAL_LIMIT": "FINANCIAL_INFORMATION",
    "INTEREST_RATE": "FINANCIAL_INFORMATION",
    "IDENTIFIER": "PERSON_IDENTIFIER", "OPERATIONAL": "FREE_TEXT_SENSITIVE",
    "TIMESTAMP": "FREE_TEXT_SENSITIVE", "DATE": "FREE_TEXT_SENSITIVE",
    "MEDICAL_ID": "MEDICAL_RECORD_NUMBER",
}

TYPE_TO_FRAMEWORKS = {
    "MEDICAL_RECORD_NUMBER": {"HIPAA"}, "HEALTH_INSURANCE_NUMBER": {"HIPAA"},
    "HEALTH_INFORMATION": {"HIPAA"}, "DIAGNOSIS_INFORMATION": {"HIPAA"},
    "PRESCRIPTION_INFORMATION": {"HIPAA"}, "CLAIM_IDENTIFIER": {"HIPAA"},
    "CLAIM_LINE_IDENTIFIER": {"HIPAA"}, "SERVICE_DATE": {"HIPAA"},
    "CREDIT_CARD_NUMBER": {"PCI_DSS"}, "BANK_ACCOUNT_NUMBER": {"GLBA"},
    "IBAN": {"GDPR"}, "IN_PAN": {"DPDP"}, "IN_AADHAAR": {"DPDP"},
    "IN_VOTER_ID": {"DPDP"}, "CANADIAN_SIN": {"PIPEDA"},
    "SOCIAL_SECURITY_NUMBER": {"CCPA_CPRA", "GLBA"},
    "US_TAX_IDENTIFIER": {"CCPA_CPRA", "GLBA"},
}
CONTEXT_FRAMEWORKS = {"GDPR", "DPDP", "CCPA_CPRA", "PIPEDA"}


def normalize_sensitive_data_type(value: Any) -> tuple[str, bool]:
    normalized = str(value or "").strip().upper().replace("-", "_").replace(" ", "_")
    normalized = TYPE_ALIASES.get(normalized, normalized)
    if normalized in APPROVED_SENSITIVE_DATA_TYPES:
        return normalized, False
    return "FREE_TEXT_SENSITIVE", True


def recommend_frameworks(classifications: list[dict[str, Any]], frameworks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    evidence: dict[str, list[dict[str, Any]]] = defaultdict(list)
    has_personal_data = False
    for row in classifications:
        if not row.get("is_sensitive", False):
            continue
        data_type, _ = normalize_sensitive_data_type(row.get("sensitive_data_type"))
        display = str(row.get("display_classification") or "").upper()
        has_personal_data = has_personal_data or display in {"PII", "PHI", "FINANCIAL", "SENSITIVE"}
        for code in TYPE_TO_FRAMEWORKS.get(data_type, set()):
            evidence[code].append({
                "classification_id": row.get("classification_id"),
                "schema_name": row.get("schema_name"), "table_name": row.get("table_name"),
                "column_name": row.get("column_name"), "sensitive_data_type": data_type,
                "confidence": float(row.get("confidence") or 0),
            })
    output = []
    for framework in frameworks:
        code = str(framework["framework_code"])
        matches = evidence.get(code, [])
        if matches:
            status = "RECOMMENDED"
            confidence = round(max(item["confidence"] for item in matches), 4)
            types = sorted({item["sensitive_data_type"] for item in matches})
            reasons = ["Detected sensitive data types associated with this framework: " + ", ".join(types)]
        elif code in CONTEXT_FRAMEWORKS and has_personal_data:
            status, confidence = "NEEDS_CONTEXT", 0.5
            reasons = ["Personal or sensitive data was detected, but regional and organizational context is required."]
        else:
            status, confidence = "NOT_INDICATED", 0.0
            reasons = ["No classification evidence currently indicates this framework."]
        output.append({
            "framework_code": code, "framework_name": framework["framework_name"],
            "implementation_status": framework["implementation_status"],
            "recommendation_status": status, "confidence": confidence,
            "reasons": reasons, "matched_columns": matches,
            "policy_version": RECOMMENDATION_POLICY_VERSION,
        })
    order = {"RECOMMENDED": 0, "NEEDS_CONTEXT": 1, "NOT_INDICATED": 2}
    return sorted(output, key=lambda item: (order[item["recommendation_status"]], item["framework_name"]))
