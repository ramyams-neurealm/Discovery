from __future__ import annotations

from collections import Counter
from typing import Any

from src.models.schemas import (
    CcpaFinding,
    ClassificationResult,
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
    "LOCATION",
    "PASSWORD",
    "BIOMETRIC",
    "EMAIL",
    "PHONE",
    "NATIONAL_ID",
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


def normalize_ccpa_finding(
    finding,
    confidence_threshold=0.8,
):
    valid_controls = {
        "CCPA-1798.100-PI",
        "CCPA-1798.105-DELETE",
        "CCPA-1798.120-OPT-OUT",
        "CCPA-1798.140-SPI",
    }

    if finding.control_code not in valid_controls:
        finding.control_code = (
            "CCPA-1798.100-PI"
        )

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


def build_ccpa_classification_findings(
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

        finding = CcpaFinding(
            control_code="CCPA-1798.140-SPI",
            severity="CRITICAL",
            table_name=table_name,
            column_name=column_name,
            issue_description=(
                "Personal or sensitive personal "
                "information was identified in column "
                f"'{column_name}', but consumer-rights "
                "and processing-purpose evidence was "
                "not collected by this discovery run."
            ),
            remediation_recommendation=(
                "Document the processing purpose, "
                "consumer notice, access and deletion "
                "mechanisms, and applicable opt-out or "
                "limit-use controls."
            ),
        )

        findings.append(finding)

    return findings


def evaluate_ccpa_controls(
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

        if control_code == "CCPA-1798.100-PI":
            if personal_data_rows:
                status = (
                    "INSUFFICIENT_EVIDENCE"
                )
                explanation = (
                    f"Identified "
                    f"{len(personal_data_rows)} "
                    "personal-data column(s), but "
                    "consumer notice and collection-"
                    "purpose evidence was not collected."
                )
                needs_human_review = True
            else:
                explanation = (
                    "No personal-data classification "
                    "evidence was found."
                )

        elif control_code == (
            "CCPA-1798.105-DELETE"
        ):
            if personal_data_rows:
                status = (
                    "INSUFFICIENT_EVIDENCE"
                )
                explanation = (
                    f"Identified "
                    f"{len(personal_data_rows)} "
                    "personal-data column(s), but "
                    "consumer deletion-request and "
                    "erasure evidence was not collected."
                )
                needs_human_review = True
            else:
                explanation = (
                    "No personal-data classification "
                    "evidence was found, so deletion-"
                    "right controls were not applied."
                )

        elif control_code == (
            "CCPA-1798.120-OPT-OUT"
        ):
            if personal_data_rows:
                status = (
                    "INSUFFICIENT_EVIDENCE"
                )
                explanation = (
                    f"Identified "
                    f"{len(personal_data_rows)} "
                    "personal-data column(s), but "
                    "opt-out or sharing-preference "
                    "evidence was not collected."
                )
                needs_human_review = True
            else:
                explanation = (
                    "No personal-data classification "
                    "evidence was found, so opt-out "
                    "controls were not applied."
                )

        elif control_code == (
            "CCPA-1798.140-SPI"
        ):
            if personal_data_rows:
                status = (
                    "INSUFFICIENT_EVIDENCE"
                )
                explanation = (
                    f"Identified "
                    f"{len(personal_data_rows)} "
                    "personal or sensitive-data "
                    "column(s), but limit-use, "
                    "disclosure, and security evidence "
                    "was not collected."
                )
                needs_human_review = True
            else:
                explanation = (
                    "No personal or sensitive-data "
                    "classification evidence was found."
                )

        elif personal_data_rows:
            status = (
                "INSUFFICIENT_EVIDENCE"
            )
            explanation = (
                "Personal data was identified, but "
                f"{evidence_type or 'required'} "
                "evidence was not collected by this "
                "discovery run."
            )
            needs_human_review = True

        else:
            explanation = (
                "No personal-data classification "
                "evidence was found for this control."
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
        status_counter[
            result["assessment_status"]
        ] += 1

    status_counts = {}

    for status in STATUSES:
        status_counts[status] = (
            status_counter.get(
                status,
                0,
            )
        )

    if applicable_count:
        risk_band = (
            "INSUFFICIENT_EVIDENCE"
        )
    else:
        risk_band = "NOT_APPLICABLE"

    summary = {
        "score": None,
        "risk_band": risk_band,
        "evidence_coverage": (
            evidence_coverage
        ),
        "applicable_controls": (
            applicable_count
        ),
        "assessed_controls": (
            assessed_count
        ),
        "status_counts": status_counts,
        "personal_data_columns_checked": len(
            personal_data_rows
        ),
        "policy_version": (
            "ccpa-cpra-control-pack-v1.0"
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
            total_points += score_points[
                result["assessment_status"]
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
            summary["risk_band"] = (
                "SERIOUS"
            )
        else:
            summary["risk_band"] = (
                "CRITICAL"
            )

    return results, summary