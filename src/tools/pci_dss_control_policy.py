from __future__ import annotations
from collections import Counter
from typing import Any

STATUSES=("PASS","FAIL","PARTIAL","INSUFFICIENT_EVIDENCE","MANUAL_REVIEW_REQUIRED","NOT_APPLICABLE","NOT_ASSESSED")
PCI_CARD_DATA_TYPES={"CREDIT_CARD_NUMBER"}

def enum_value(value: Any)->str:
    return str(getattr(value,"value",value) or "").strip().upper()

def evaluate_pci_dss_controls(controls:list[dict[str,Any]],classifications:list[dict[str,Any]])->tuple[list[dict[str,Any]],dict[str,Any]]:
    card_rows=[row for row in classifications if bool(row.get("is_sensitive",True)) and enum_value(row.get("sensitive_data_type")) in PCI_CARD_DATA_TYPES]
    results=[]
    for control in controls:
        if enum_value(control.get("evaluation_type"))=="CARD_DATA_DISCOVERY":
            if card_rows:
                status="PASS"; explanation=f"Identified {len(card_rows)} column(s) classified as payment-card data."
                confidence=max(float(row.get("confidence") or 0) for row in card_rows)
                review=any(bool(row.get("needs_human_review")) for row in card_rows)
            else:
                status="NOT_APPLICABLE"; explanation="No payment-card classification evidence was found."; confidence=1.0; review=False
        elif not card_rows:
            status="NOT_APPLICABLE"; explanation="No payment-card data was identified, so this control was not applied to the database assessment."; confidence=1.0; review=False
        else:
            status="INSUFFICIENT_EVIDENCE"; explanation=f"Payment-card data exists, but {control['evidence_type']} evidence was not collected by this discovery run."; confidence=1.0; review=True
        results.append({"control_code":control["control_code"],"control_title":control["control_title"],"assessment_status":status,"severity":enum_value(control["default_severity"]),"explanation":explanation,"confidence":confidence,"needs_human_review":review})
    applicable=[r for r in results if r["assessment_status"]!="NOT_APPLICABLE"]
    assessed=[r for r in applicable if r["assessment_status"] in {"PASS","PARTIAL","FAIL"}]
    coverage=round(100*len(assessed)/len(applicable),2) if applicable else 100.0
    counts=Counter(r["assessment_status"] for r in results)
    score=None
    if not applicable: risk_band="NOT_APPLICABLE"
    elif coverage<50: risk_band="INSUFFICIENT_EVIDENCE"
    else:
        points={"PASS":100.0,"PARTIAL":50.0,"FAIL":0.0}
        score=round(sum(points[r["assessment_status"]] for r in assessed)/len(assessed),2)
        risk_band="GOOD" if score>=85 else "NEEDS_REVIEW" if score>=60 else "SERIOUS" if score>=30 else "CRITICAL"
    return results,{"score":score,"risk_band":risk_band,"evidence_coverage":coverage,"applicable_controls":len(applicable),"assessed_controls":len(assessed),"status_counts":{s:counts.get(s,0) for s in STATUSES},"card_data_columns_checked":len(card_rows),"policy_version":"pci-dss-control-pack-v1"}


def build_pci_dss_classification_findings(
    classifications: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Build one column-level finding per detected card-number classification."""
    findings: list[dict[str, Any]] = []
    for row in classifications:
        if not bool(row.get("is_sensitive", True)):
            continue
        if enum_value(row.get("sensitive_data_type")) not in PCI_CARD_DATA_TYPES:
            continue
        column_name = str(row.get("column_name") or "unknown_column")
        needs_review = bool(row.get("needs_human_review", False))
        findings.append({
            "classification_id": int(row["classification_id"]),
            "severity": "NEEDS_REVIEW",
            "assessment_status": "INSUFFICIENT_EVIDENCE",
            "finding": (
                f"The column '{column_name}' contains payment-card data "
                "that is relevant to PCI DSS scope."
            ),
            "recommendation": (
                "Verify storage protection, access restrictions, transmission "
                "security, logging, vulnerability management, and periodic "
                "security testing for this payment-card data."
            ),
            "confidence": float(row.get("confidence") or 0),
            "needs_human_review": needs_review,
            "review_reason": row.get("review_reason"),
            "verification_status": "PROVISIONAL",
            "source_finding_type": "PCI_CLASSIFICATION",
            "source_finding_id": int(row["classification_id"]),
        })
    return findings
