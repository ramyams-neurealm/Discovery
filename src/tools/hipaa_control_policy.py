from __future__ import annotations

from collections import Counter
from typing import Any
from src.tools.access_policy_evaluator import (
    evaluate_database_access_policy,
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


def enum_value(value: Any) -> str:
    return str(getattr(value, "value", value) or "").strip().upper()


def _evaluate_database_permissions(
    security_evidence: list[dict[str, Any]],
    policy_context: list[dict[str, Any]] | None = None,
) -> tuple[str, str, float, bool, dict[str, Any]]:
    return evaluate_database_access_policy(
        security_evidence,
        policy_context or [],
    )


def evaluate_hipaa_controls(
    controls: list[dict[str, Any]],
    classifications: list[dict[str, Any]],
    security_evidence: list[dict[str, Any]] | None = None,
    policy_context: list[dict[str, Any]] | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    phi = [
        row
        for row in classifications
        if enum_value(row.get("display_classification")) == "PHI"
    ]
    evidence = security_evidence or []
    results = []

    for control in controls:
        trace: dict[str, Any] | None = None
        if control["evaluation_type"] == "PHI_DISCOVERY":
            status = "PASS" if phi else "NOT_APPLICABLE"
            explanation = (
                f"Identified {len(phi)} column(s) classified as PHI."
                if phi
                else "No PHI classification evidence was found."
            )
            confidence = max(
                (float(row.get("confidence") or 0) for row in phi),
                default=1.0,
            )
            review = any(
                bool(row.get("needs_human_review")) for row in phi
            )
        elif not phi:
            status = "NOT_APPLICABLE"
            explanation = (
                "No PHI was identified, so this safeguard control "
                "was not applied."
            )
            confidence = 1.0
            review = False
        elif control["evidence_type"] == "DATABASE_PERMISSIONS":
            status, explanation, confidence, review, trace = (
                _evaluate_database_permissions(
                    evidence,
                    policy_context,
                )
            )
        else:
            status = "INSUFFICIENT_EVIDENCE"
            explanation = (
                f"PHI exists, but {control['evidence_type']} evidence "
                "was not collected by this discovery run."
            )
            confidence = 1.0
            review = True

        results.append(
            {
                "control_code": control["control_code"],
                "control_title": control["control_title"],
                "assessment_status": status,
                "severity": enum_value(control["default_severity"]),
                "explanation": explanation,
                "confidence": confidence,
                "needs_human_review": review,
                **(
                    {"decision_trace": trace}
                    if trace is not None
                    else {}
                ),
            }
        )

    applicable = [
        result
        for result in results
        if result["assessment_status"] != "NOT_APPLICABLE"
    ]
    assessed = [
        result
        for result in applicable
        if result["assessment_status"] in {"PASS", "PARTIAL", "FAIL"}
    ]
    coverage = (
        round(100 * len(assessed) / len(applicable), 2)
        if applicable
        else 100.0
    )
    counts = Counter(
        result["assessment_status"] for result in results
    )
    summary = {
        "score": None,
        "risk_band": (
            "NOT_APPLICABLE"
            if not applicable
            else "INSUFFICIENT_EVIDENCE"
        ),
        "evidence_coverage": coverage,
        "applicable_controls": len(applicable),
        "assessed_controls": len(assessed),
        "status_counts": {
            status: counts.get(status, 0) for status in STATUSES
        },
        "phi_columns_checked": len(phi),
        "policy_version": "hipaa-control-pack-v1.2",
    }

    if applicable and coverage >= 50:
        points = {"PASS": 100.0, "PARTIAL": 50.0, "FAIL": 0.0}
        summary["score"] = round(
            sum(
                points[result["assessment_status"]]
                for result in assessed
            )
            / len(assessed),
            2,
        )
        score = summary["score"]
        summary["risk_band"] = (
            "GOOD"
            if score >= 85
            else "NEEDS_REVIEW"
            if score >= 60
            else "SERIOUS"
            if score >= 30
            else "CRITICAL"
        )

    return results, summary
