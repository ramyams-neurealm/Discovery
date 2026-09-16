from __future__ import annotations
from collections import Counter
from typing import Any

STATUSES = ("PASS", "FAIL", "PARTIAL", "INSUFFICIENT_EVIDENCE", "MANUAL_REVIEW_REQUIRED", "NOT_APPLICABLE", "NOT_ASSESSED")


def enum_value(value: Any) -> str:
    return str(getattr(value, "value", value) or "").strip().upper()


def evaluate_hipaa_controls(controls: list[dict[str, Any]], classifications: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    phi = [row for row in classifications if enum_value(row.get("display_classification")) == "PHI"]
    results = []
    for control in controls:
        if control["evaluation_type"] == "PHI_DISCOVERY":
            status = "PASS" if phi else "NOT_APPLICABLE"
            explanation = f"Identified {len(phi)} column(s) classified as PHI." if phi else "No PHI classification evidence was found."
            confidence = max((float(row.get("confidence") or 0) for row in phi), default=1.0)
            review = any(bool(row.get("needs_human_review")) for row in phi)
        elif not phi:
            status, explanation, confidence, review = "NOT_APPLICABLE", "No PHI was identified, so this safeguard control was not applied.", 1.0, False
        else:
            status = "INSUFFICIENT_EVIDENCE"
            explanation = f"PHI exists, but {control['evidence_type']} evidence was not collected by this discovery run."
            confidence, review = 1.0, True
        results.append({"control_code": control["control_code"], "control_title": control["control_title"], "assessment_status": status, "severity": enum_value(control["default_severity"]), "explanation": explanation, "confidence": confidence, "needs_human_review": review})
    applicable = [r for r in results if r["assessment_status"] != "NOT_APPLICABLE"]
    assessed = [r for r in applicable if r["assessment_status"] in {"PASS", "PARTIAL", "FAIL"}]
    coverage = round(100 * len(assessed) / len(applicable), 2) if applicable else 100.0
    counts = Counter(r["assessment_status"] for r in results)
    summary = {"score": None, "risk_band": "NOT_APPLICABLE" if not applicable else "INSUFFICIENT_EVIDENCE", "evidence_coverage": coverage, "applicable_controls": len(applicable), "assessed_controls": len(assessed), "status_counts": {s: counts.get(s, 0) for s in STATUSES}, "phi_columns_checked": len(phi), "policy_version": "hipaa-control-pack-v1.1"}
    if applicable and coverage >= 50:
        points = {"PASS": 100.0, "PARTIAL": 50.0, "FAIL": 0.0}
        summary["score"] = round(sum(points[r["assessment_status"]] for r in assessed) / len(assessed), 2)
        score = summary["score"]
        summary["risk_band"] = "GOOD" if score >= 85 else "NEEDS_REVIEW" if score >= 60 else "SERIOUS" if score >= 30 else "CRITICAL"
    return results, summary
