from __future__ import annotations

from collections import Counter

from src.models.schemas import GdprFinding


STATUSES = (
    "PASS",
    "FAIL",
    "PARTIAL",
    "INSUFFICIENT_EVIDENCE",
    "MANUAL_REVIEW_REQUIRED",
    "NOT_APPLICABLE",
    "NOT_ASSESSED",
)


PERSONAL_DATA_CLASSIFICATIONS = {
    "PII",
    "SENSITIVE",
    "PHI",
    "EMAIL",
    "PHONE",
    "NATIONAL_ID",
    "LOCATION",
    "BIOMETRIC",
    "EMPLOYEE",
    "PASSWORD",
}


SPECIAL_CATEGORY_CLASSIFICATIONS = {
    "SENSITIVE",
    "PHI",
    "BIOMETRIC",
}


def _enum_value(value):
    return str(
        getattr(value, "value", value) or ""
    ).strip().upper()


def _get_classification_str(classification):
    if isinstance(classification, dict):
        raw_value = (
            classification.get(
                "display_classification"
            )
            or classification.get(
                "classification"
            )
            or ""
        )
    else:
        raw_value = getattr(
            classification,
            "display_classification",
            getattr(
                classification,
                "classification",
                "",
            ),
        )

    return _enum_value(raw_value)


def normalize_gdpr_finding(
    finding,
    confidence_threshold=0.8,
):
    """
    Normalize GDPR control codes and severity values.
    """

    valid_controls = {
        "GDPR-ART-6",
        "GDPR-ART-9",
        "GDPR-ART-32",
    }

    if finding.control_code not in valid_controls:
        finding.control_code = "GDPR-ART-32"

    finding.severity = _enum_value(
        finding.severity
    )

    if finding.severity not in {
        "CRITICAL",
        "SERIOUS",
        "WARNING",
    }:
        finding.severity = "SERIOUS"

    del confidence_threshold

    return finding


def evaluate_gdpr_controls(
    controls,
    classifications,
):
    """
    Evaluate GDPR controls using discovered classification evidence.

    The workflow can identify potentially applicable personal data,
    but evidence such as lawful-processing records, explicit consent,
    and technical safeguard documentation requires separate proof.
    """

    personal_data_rows = []
    special_category_rows = []

    for classification in classifications:
        classification_value = (
            _get_classification_str(
                classification
            )
        )

        if (
            classification_value
            in PERSONAL_DATA_CLASSIFICATIONS
        ):
            personal_data_rows.append(
                classification
            )

        if (
            classification_value
            in SPECIAL_CATEGORY_CLASSIFICATIONS
        ):
            special_category_rows.append(
                classification
            )

    results = []

    for control in controls:
        control_code = str(
            control.get("control_code") or ""
        ).strip().upper()

        control_title = str(
            control.get("control_title") or ""
        ).strip()

        evidence_type = str(
            control.get("evidence_type") or ""
        ).strip().upper()

        default_severity = _enum_value(
            control.get("default_severity")
            or "NEEDS_REVIEW"
        )

        status = "NOT_APPLICABLE"
        confidence = 1.0
        needs_human_review = False

        if control_code == "GDPR-ART-6":
            if personal_data_rows:
                status = "INSUFFICIENT_EVIDENCE"
                explanation = (
                    f"Identified {len(personal_data_rows)} "
                    "personal-data column(s), but lawful-"
                    "processing basis, purpose limitation, "
                    "and consent evidence was not collected "
                    "by this discovery run."
                )
                needs_human_review = True
            else:
                explanation = (
                    "No personal-data classification "
                    "evidence was found, so the lawful-"
                    "processing control was not applicable."
                )

        elif control_code == "GDPR-ART-9":
            if special_category_rows:
                status = "INSUFFICIENT_EVIDENCE"
                explanation = (
                    f"Identified "
                    f"{len(special_category_rows)} "
                    "special-category data column(s), but "
                    "explicit consent, legal exception, or "
                    "other Article 9 processing evidence "
                    "was not collected."
                )
                needs_human_review = True
            else:
                explanation = (
                    "No special-category personal-data "
                    "classification evidence was found."
                )

        elif control_code == "GDPR-ART-32":
            if personal_data_rows:
                status = "INSUFFICIENT_EVIDENCE"
                explanation = (
                    f"Identified {len(personal_data_rows)} "
                    "personal-data column(s), but technical "
                    "and organizational security evidence "
                    "was not collected by this discovery run."
                )
                needs_human_review = True
            else:
                explanation = (
                    "No personal-data classification "
                    "evidence was found, so the security-"
                    "of-processing control was not applied."
                )

        elif personal_data_rows:
            status = "INSUFFICIENT_EVIDENCE"
            explanation = (
                "Personal data was identified, but "
                f"{evidence_type or 'required'} evidence "
                "was not collected by this discovery run."
            )
            needs_human_review = True

        else:
            explanation = (
                "No applicable personal-data classification "
                "evidence was found for this control."
            )

        results.append(
            {
                "control_code": control_code,
                "control_title": control_title,
                "assessment_status": status,
                "severity": default_severity,
                "explanation": explanation,
                "confidence": confidence,
                "needs_human_review": (
                    needs_human_review
                ),
            }
        )

    applicable_results = []

    for result in results:
        if (
            result["assessment_status"]
            != "NOT_APPLICABLE"
        ):
            applicable_results.append(result)

    assessed_results = []

    for result in applicable_results:
        if result["assessment_status"] in {
            "PASS",
            "PARTIAL",
            "FAIL",
        }:
            assessed_results.append(result)

    applicable_count = len(
        applicable_results
    )

    assessed_count = len(
        assessed_results
    )

    if applicable_count:
        evidence_coverage = round(
            100
            * assessed_count
            / applicable_count,
            2,
        )
    else:
        evidence_coverage = 100.0

    status_counter = Counter()

    for result in results:
        result_status = result[
            "assessment_status"
        ]

        status_counter[result_status] += 1

    status_counts = {}

    for status in STATUSES:
        status_counts[status] = (
            status_counter.get(
                status,
                0,
            )
        )

    if applicable_count:
        risk_band = "INSUFFICIENT_EVIDENCE"
    else:
        risk_band = "NOT_APPLICABLE"

    summary = {
        "score": None,
        "risk_band": risk_band,
        "evidence_coverage": evidence_coverage,
        "applicable_controls": applicable_count,
        "assessed_controls": assessed_count,
        "status_counts": status_counts,
        "personal_data_columns_checked": len(
            personal_data_rows
        ),
        "special_category_columns_checked": len(
            special_category_rows
        ),
        "policy_version": (
            "gdpr-control-pack-v1.0"
        ),
    }

    if (
        applicable_count
        and assessed_count
        and evidence_coverage >= 50
    ):
        score_points = {
            "PASS": 100.0,
            "PARTIAL": 50.0,
            "FAIL": 0.0,
        }

        total_points = 0.0

        for result in assessed_results:
            result_status = result[
                "assessment_status"
            ]

            total_points += score_points[
                result_status
            ]

        score = round(
            total_points / assessed_count,
            2,
        )

        summary["score"] = score

        if score >= 85:
            summary["risk_band"] = "GOOD"
        elif score >= 60:
            summary["risk_band"] = (
                "NEEDS_REVIEW"
            )
        elif score >= 30:
            summary["risk_band"] = "SERIOUS"
        else:
            summary["risk_band"] = "CRITICAL"

    return results, summary