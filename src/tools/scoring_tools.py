from collections import Counter
from src.models.enums import HipaaSeverity
from src.models.schemas import HipaaFinding, HipaaScore

SCORES = {
    HipaaSeverity.GOOD: 100.0,
    HipaaSeverity.NEEDS_REVIEW: 70.0,
    HipaaSeverity.SERIOUS: 35.0,
    HipaaSeverity.CRITICAL: 0.0,
}


def calculate_hipaa_score(findings: list[HipaaFinding]) -> HipaaScore:
    if not findings:
        return HipaaScore(
            score=100.0,
            risk_band="NOT_APPLICABLE",
            phi_columns_checked=0,
            severity_counts={s.value: 0 for s in HipaaSeverity},
            policy_version="hipaa-score-v1",
        )
    score = sum(SCORES[f.severity] for f in findings) / len(findings)
    if score >= 85:
        band = "GOOD"
    elif score >= 60:
        band = "NEEDS_REVIEW"
    elif score >= 30:
        band = "SERIOUS"
    else:
        band = "CRITICAL"
    counts = Counter(f.severity.value for f in findings)
    return HipaaScore(
        score=round(score, 2),
        risk_band=band,
        phi_columns_checked=len(findings),
        severity_counts={s.value: counts.get(s.value, 0) for s in HipaaSeverity},
        policy_version="hipaa-score-v1",
    )

from src.models.schemas import GdprFinding, GdprScore

def calculate_gdpr_score(findings: list[GdprFinding]) -> GdprScore:
    """Calculates overall GDPR compliance score based on finding severity deductions."""
    if not findings:
        return GdprScore(overall_score=100, status_band="COMPLIANT")
        
    deductions = 0
    for finding in findings:
        if finding.severity == "CRITICAL":
            deductions += 25
        elif finding.severity == "SERIOUS":
            deductions += 15
        else:
            deductions += 5
            
    overall_score = max(0, 100 - deductions)
    
    if overall_score >= 85:
        status_band = "COMPLIANT"
    elif overall_score >= 60:
        status_band = "NEEDS_ATTENTION"
    else:
        status_band = "NON_COMPLIANT"
        
    return GdprScore(overall_score=overall_score, status_band=status_band)

def calculate_generic_framework_score(findings: list) -> tuple[int, str]:
    if not findings:
        return 100, "COMPLIANT"
    
    deductions = sum(
        25 if getattr(f, "severity", "").upper() == "CRITICAL"
        else 15 if getattr(f, "severity", "").upper() == "SERIOUS"
        else 5 
        for f in findings
    )
    
    overall_score = max(0, 100 - deductions)
    band = (
        "COMPLIANT" if overall_score >= 85 
        else "NEEDS_ATTENTION" if overall_score >= 60 
        else "NON_COMPLIANT"
    )
    return overall_score, band