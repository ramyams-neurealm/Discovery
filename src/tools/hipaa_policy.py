from src.models.enums import HipaaSeverity

REVIEW_SEVERITIES = {HipaaSeverity.NEEDS_REVIEW, HipaaSeverity.SERIOUS, HipaaSeverity.CRITICAL}
NEUTRAL_RECOMMENDATION = (
    "Obtain and review evidence of applicable encryption, masking, access-control, "
    "audit, and retention controls. If evidence confirms a control gap, create and "
    "track an appropriate remediation plan."
)


def normalize_hipaa_finding(finding, confidence_threshold: float):
    finding.verification_status = "PROVISIONAL"
    if finding.severity in REVIEW_SEVERITIES or finding.confidence < confidence_threshold:
        finding.needs_human_review = True
        finding.review_reason = finding.review_reason or (
            "Human review is required because applicable controls could not be "
            "verified from the supplied metadata."
        )
    recommendation = finding.recommendation.lower()
    unsupported = ("implement encryption", "implement and verify", "ensure that", "ensure '", "protect with encryption")
    if any(phrase in recommendation for phrase in unsupported):
        finding.recommendation = NEUTRAL_RECOMMENDATION
    return finding
