from __future__ import annotations
from collections import Counter
from typing import Any

STATUSES = ("PASS", "FAIL", "PARTIAL", "INSUFFICIENT_EVIDENCE", "MANUAL_REVIEW_REQUIRED", "NOT_APPLICABLE", "NOT_ASSESSED")

def enum_value(value: Any) -> str:
    return str(getattr(value, "value", value) or "").strip().upper()

def evaluate_gdpr_controls(controls: list[dict[str, Any]], classifications: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    # Establish applicability using PII classifications
    pii = [row for row in classifications if enum_value(row.get("display_classification")) == "PII"]
    results = []
    
    for control in controls:
        if control.get("evaluation_type") == "PII_DISCOVERY":
            status = "PASS" if pii else "NOT_APPLICABLE"
            explanation = f"Identified {len(pii)} column(s) classified as PII." if pii else "No PII classification evidence was found."
            confidence = max((float(row.get("confidence") or 0) for row in pii), default=1.0)
            review = any(bool(row.get("needs_human_review")) for row in pii)
        elif not pii:
            status, explanation, confidence, review = "NOT_APPLICABLE", "No PII was identified, so this safeguard control was not applied.", 1.0, False
        else:
            # Missing evidence maps strictly to INSUFFICIENT_EVIDENCE
            status = "INSUFFICIENT_EVIDENCE"
            explanation = f"PII exists, but {control.get('evidence_type')} evidence was not collected by this discovery run."
            confidence, review = 1.0, True
            
        results.append({
            "control_code": control["control_code"],
            "control_title": control["control_title"],
            "assessment_status": status,
            "severity": enum_value(control.get("default_severity", "NEEDS_REVIEW")),
            "explanation": explanation,
            "confidence": confidence,
            "needs_human_review": review
        })
        
    applicable = [r for r in results if r["assessment_status"] != "NOT_APPLICABLE"]
    assessed = [r for r in applicable if r["assessment_status"] in {"PASS", "PARTIAL", "FAIL"}]
    coverage = round(100 * len(assessed) / len(applicable), 2) if applicable else 100.0
    counts = Counter(r["assessment_status"] for r in results)
    
    summary = {
        "score": None,
        "risk_band": "NOT_APPLICABLE" if not applicable else "INSUFFICIENT_EVIDENCE",
        "evidence_coverage": coverage,
        "applicable_controls": len(applicable),
        "assessed_controls": len(assessed),
        "status_counts": {s: counts.get(s, 0) for s in STATUSES},
        "pii_columns_checked": len(pii),
        "policy_version": "gdpr-control-pack-v1.0"
    }
    
    # 50% Guardrail for scoring
    if applicable and coverage >= 50:
        points = {"PASS": 100.0, "PARTIAL": 50.0, "FAIL": 0.0}
        summary["score"] = round(sum(points[r["assessment_status"]] for r in assessed) / len(assessed), 2)
        score = summary["score"]
        summary["risk_band"] = "GOOD" if score >= 85 else "NEEDS_REVIEW" if score >= 60 else "SERIOUS" if score >= 30 else "CRITICAL"
        
    return results, summary

def build_gdpr_classification_findings(classifications: list[dict[str, Any]]) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    
    for row in classifications:
        if enum_value(row.get("display_classification")) != "PII":
            continue
            
        column_name = str(row.get("column_name") or "unknown_column")
        needs_review = bool(row.get("needs_human_review", False))
        
        findings.append({
            "classification_id": int(row.get("classification_id", 0)),
            "severity": "NEEDS_REVIEW",
            "assessment_status": "INSUFFICIENT_EVIDENCE",
            "finding": f"The column '{column_name}' contains personal data (PII) relevant to GDPR scope.",
            "recommendation": "Verify storage protection, access restrictions, transmission security, data erasure, and logging capabilities for this personal data.",
            "confidence": float(row.get("confidence") or 0),
            "needs_human_review": needs_review,
            "review_reason": row.get("review_reason"),
            "verification_status": "PROVISIONAL",
            "source_finding_type": "GDPR_CLASSIFICATION",
            "source_finding_id": int(row.get("classification_id", 0)),
        })
        
    return findings