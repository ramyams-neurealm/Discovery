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
