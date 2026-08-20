from src.models.enums import HipaaSeverity
from src.models.schemas import HipaaFinding
from src.tools.scoring_tools import calculate_hipaa_score


def finding(severity: HipaaSeverity) -> HipaaFinding:
    return HipaaFinding(
        table_name="patients",
        column_name="value",
        severity=severity,
        finding="Finding text",
        recommendation="Recommendation text",
        confidence=0.9,
        needs_human_review=False,
    )


def test_score_is_deterministic():
    findings = [
        finding(HipaaSeverity.CRITICAL),
        finding(HipaaSeverity.SERIOUS),
        finding(HipaaSeverity.NEEDS_REVIEW),
        finding(HipaaSeverity.GOOD),
    ]
    first = calculate_hipaa_score(findings)
    second = calculate_hipaa_score(findings)
    assert first == second
    assert first.score == 51.25
