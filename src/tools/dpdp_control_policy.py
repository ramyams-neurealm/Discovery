from __future__ import annotations

from collections import Counter
from typing import Any

from src.models.schemas import (
    ClassificationResult,
    DpdpFinding,
)


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
    "EMAIL",
    "NATIONAL_ID",
    "PHONE",
}


def _enum_value(value: Any) -> str:
    return str(
        getattr(value, "value", value) or ""
    ).strip().upper()


def _get_classification_str(
    classification: Any,
) -> str:
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


def _get_value(
    item: Any,
    field_name: str,
    default: Any = None,
) -> Any:
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


def normalize_dpdp_finding(
    finding: DpdpFinding,
    confidence_threshold: float = 0.8,
) -> DpdpFinding:
    valid_controls = {
        "DPDP-SEC-6",
        "DPDP-SEC-8",
        "DPDP-SEC-9",
    }

    if finding.control_code not in valid_controls:
        finding.control_code = "DPDP-SEC-6"

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


def build_dpdp_classification_findings(
    classifications: list[ClassificationResult],
) -> list[DpdpFinding]:
    findings: list[DpdpFinding] = []

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

        findings.append(
            DpdpFinding(
                control_code="DPDP-SEC-6",
                severity="SERIOUS",
                table_name=table_name,
                column_name=column_name,
                issue_description=(
                    "Digital dentified "
                    f"in column '{column_name}', but consent "
                    "or lawful-processing evidence was not "
                    "collected by this discovery run."
                ),
                remediation_recommendation=(
                    "Record the applicable consent, notice, "
                    "or lawful-processing basis and retain "
                    "verifiable evidence for the identified "
                    "personal-data processing activity."
                ),
            )
        )

    return findings


def evaluate_dpdp_controls(
    controls: list[dict[str, Any]],
    classifications: list[dict[str, Any]],
) -> tuple[
    list[dict[str, Any]],
    dict[str, Any],
]:
    personal_data_rows = [
        classification
        for classification in classifications
        if (
            _get_classification_str(
                classification
            )
            in PERSONAL_DATA_CLASSIFICATIONS
        )
    ]

    results: list[dict[str, Any]] = []

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
            or "SERIOUS"
        )

        if control_code == "DPDP-SEC-6":
            if personal_data_rows:
                status = "INSUFFICIENT_EVIDENCE"
                explanation = (
                    f"Identified {len(personal_data_rows)} "
                    "personal-data column(s), but consent "
                    "or lawful-processing evidence was not "
                    "collected by this discovery run."
                )
                confidence = 1.0
                needs_human_review = True
            else:
                status = "NOT_APPLICABLE"
                explanation = (
                    "No personal-data classification "
                    "evidence was found."
                )
                confidence = 1.0
                needs_human_review = False

        elif control_code == "DPDP-SEC-8":
            if personal_data_rows:
                status = "INSUFFICIENT_EVIDENCE"
                explanation = (
                    f"Identified {len(personal_data_rows)} "
                    "personal-data column(s), but technical "
                    "and organizational safeguard evidence "
                    "was not collected."
                )
                confidence = 1.0
                needs_human_review = True
            else:
                status = "NOT_APPLICABLE"
                explanation = (
                    "No personal-data classification "
                    "evidence was found, so the security "
                    "safeguard control was not applied."
                )
                confidence = 1.0
                needs_human_review = False

        elif control_code == "DPDP-SEC-9":
            if personal_data_rows:
                status = "INSUFFICIENT_EVIDENCE"
                explanation = (
                    f"Identified {len(personal_data_rows)} "
                    "personal-data column(s), but retention, "
                    "erasure, and deletion-policy evidence "
                    "was not collected."
                )
                confidence = 1.0
                needs_human_review = True
            else:
                status = "NOT_APPLICABLE"
                explanation = (
                    "No personal-data classification "
                    "evidence was found, so the retention "
                    "and erasure control was not applied."
                )
                confidence = 1.0
                needs_human_review = False

        elif personal_data_rows:
            status = "INSUFFICIENT_EVIDENCE"
            explanation = (
                "Personal data was identified, but "
                f"{evidence_type or 'required'} evidence "
                "was not collected by this discovery run."
            )
            confidence = 1.0
            needs_human_review = True

        else:
            status = "NOT_APPLICABLE"
            explanation = (
                "No personal-data classification evidence "
                "was found for this control."
            )
            confidence = 1.0
            needs_human_review = False

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

    applicable_results = [
        result
        for result in results
        if (
            result["assessment_status"]
            != "NOT_APPLICABLE"
        )
    ]

    assessed_results = [
        result
        for result in applicable_results
        if result["assessment_status"]
        in {
            "PASS",
            "PARTIAL",
            "FAIL",
        }
    ]

    applicable_count = len(
        applicable_results
    )

    assessed_count = len(
        assessed_results
    )

    evidence_coverage = (
        round(
            100
            * assessed_count
            / applicable_count,
            2,
        )
        if applicable_count
        else 100.0
    )

    status_counts = Counter(
        result["assessment_status"]
        for result in results
    )

    summary: dict[str, Any] = {
        "score": None,
        "risk_band": (
            "NOT_APPLICABLE"
            if not applicable_results
            else "INSUFFICIENT_EVIDENCE"
        ),
        "evidence_coverage": evidence_coverage,
        "applicable_controls": applicable_count,
        "assessed_controls": assessed_count,
        "status_counts": {
            status: status_counts.get(
                status,
                0,
            )
            for status in STATUSES
        },
        "personal_data_columns_checked": len(
            personal_data_rows
        ),
        "policy_version": (
            "dpdp-control-pack-v1.0"
        ),
    }

    if (
        applicable_results
        and assessed_results
        and evidence_coverage >= 50
    ):
        score_points = {
            "PASS": 100.0,
            "PARTIAL": 50.0,
            "FAIL": 0.0,
        }

        score = round(
            sum(
                score_points[
                    result[
                        "assessment_status"
                    ]
                ]
                for result in assessed_results
            )
            / assessed_count,
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