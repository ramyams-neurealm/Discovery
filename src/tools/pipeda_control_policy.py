from __future__ import annotations

from collections import Counter

from src.models.schemas import PipedaFinding


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
    "EMPLOYEE",
    "NATIONAL_ID",
    "EMAIL",
    "PHONE",
    "LOCATION",
    "BIOMETRIC",
}


def _enum_value(value):
    return str(
        getattr(value, "value", value) or ""
    ).strip().upper()


def _get_classification_str(classification):
    if isinstance(classification, dict):
        raw_value = (
            classification.get("display_classification")
            or classification.get("classification")
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


def _get_value(
    item,
    field_name,
    default=None,
):
    if isinstance(item, dict):
        return item.get(
            field_name,
            default,
        )

    return getattr(
        item,
        field_name,
        default,
    )


def normalize_pipeda_finding(
    finding,
    confidence_threshold=0.8,
):
    valid_controls = {
        "PIPEDA-PRIN-4.3",
        "PIPEDA-PRIN-4.5",
        "PIPEDA-PRIN-4.7",
        "PIPEDA-PRIN-4.9",
    }

    if finding.control_code not in valid_controls:
        finding.control_code = "PIPEDA-PRIN-4.7"

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


def build_pipeda_classification_findings(
    classifications,
):
    findings = []

    for classification in classifications:
        classification_value = (
            _get_classification_str(
                classification
            )
        )

        if (
            classification_value
            not in PERSONAL_DATA_CLASSIFICATIONS
        ):
            continue

        table_name = str(
            _get_value(
                classification,
                "table_name",
                "",
            )
            or ""
        )

        column_name = str(
            _get_value(
                classification,
                "column_name",
                "",
            )
            or ""
        )

        finding = PipedaFinding(
            control_code="PIPEDA-PRIN-4.7",
            severity="CRITICAL",
            table_name=table_name,
            column_name=column_name,
            issue_description=(
                "Personal information was identified "
                f"in column '{column_name}', but "
                "technological safeguard evidence was "
                "not collected by this discovery run."
            ),
            remediation_recommendation=(
                "Implement safeguards appropriate to "
                "the sensitivity of the information, "
                "including access controls, encryption, "
                "monitoring, retention, and secure "
                "disposal measures."
            ),
        )

        findings.append(finding)

    return findings


def evaluate_pipeda_controls(
    controls,
    classifications,
):
    personal_data_rows = []

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

        if control_code == "PIPEDA-PRIN-4.3":
            if personal_data_rows:
                status = "INSUFFICIENT_EVIDENCE"
                explanation = (
                    f"Identified {len(personal_data_rows)} "
                    "personal-information column(s), "
                    "but consent and processing-purpose "
                    "evidence was not collected."
                )
                needs_human_review = True
            else:
                explanation = (
                    "No personal-information "
                    "classification evidence was found."
                )

        elif control_code == "PIPEDA-PRIN-4.5":
            if personal_data_rows:
                status = "INSUFFICIENT_EVIDENCE"
                explanation = (
                    f"Identified {len(personal_data_rows)} "
                    "personal-information column(s), "
                    "but retention, limitation-of-use, "
                    "and secure-disposal evidence was "
                    "not collected."
                )
                needs_human_review = True
            else:
                explanation = (
                    "No personal-information evidence "
                    "was found, so retention controls "
                    "were not applied."
                )

        elif control_code == "PIPEDA-PRIN-4.7":
            if personal_data_rows:
                status = "INSUFFICIENT_EVIDENCE"
                explanation = (
                    f"Identified {len(personal_data_rows)} "
                    "personal-information column(s), "
                    "but administrative, technical, and "
                    "physical safeguard evidence was "
                    "not collected."
                )
                needs_human_review = True
            else:
                explanation = (
                    "No personal-information evidence "
                    "was found, so safeguard controls "
                    "were not applied."
                )

        elif control_code == "PIPEDA-PRIN-4.9":
            if personal_data_rows:
                status = "INSUFFICIENT_EVIDENCE"
                explanation = (
                    f"Identified {len(personal_data_rows)} "
                    "personal-information column(s), "
                    "but individual access, correction, "
                    "and request-handling evidence was "
                    "not collected."
                )
                needs_human_review = True
            else:
                explanation = (
                    "No personal-information evidence "
                    "was found, so individual-access "
                    "controls were not applied."
                )

        elif personal_data_rows:
            status = "INSUFFICIENT_EVIDENCE"
            explanation = (
                "Personal information was identified, "
                f"but {evidence_type or 'required'} "
                "evidence was not collected by this "
                "discovery run."
            )
            needs_human_review = True

        else:
            explanation = (
                "No personal-information "
                "classification evidence was found "
                "for this control."
            )

        result = {
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

        results.append(result)

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

    for allowed_status in STATUSES:
        status_counts[allowed_status] = (
            status_counter.get(
                allowed_status,
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
        "policy_version": (
            "pipeda-control-pack-v1.0"
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