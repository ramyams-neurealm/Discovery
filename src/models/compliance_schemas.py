from enum import Enum
from typing import Literal
from pydantic import BaseModel, Field


class ComplianceStatus(str, Enum):
    CRITICAL = "Critical"
    SERIOUS = "Serious"
    NEEDS_REVIEW = "Needs review"
    GOOD = "Good"

class AssessmentStatus(str, Enum):
    ASSESSED = "ASSESSED"
    NO_COLUMNS_IN_SCOPE = "NO_COLUMNS_IN_SCOPE"
    EVALUATION_FAILED = "EVALUATION_FAILED"


class RiskBand(str, Enum):
    GOOD = "GOOD"
    MODERATE_RISK = "MODERATE_RISK"
    SERIOUS_RISK = "SERIOUS_RISK"
    CRITICAL_RISK = "CRITICAL_RISK"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class ColumnComplianceFinding(BaseModel):
    """Evaluation result for a single column under a specific framework."""
    table_name: str = Field(default="", description="Name of the table containing the column")
    column_name: str = Field(description="Name of the evaluated column")
    status: Literal["Good", "Needs review", "Serious", "Critical"] = Field(
        description="Must be strictly Good, Needs review, Serious, or Critical"
    )
    finding: str = Field(
        description="Clear statutory violation explanation citing the framework context"
    )
    recommendation: str = Field(
        description="Actionable technical remedy (e.g., tokenization, AES-256, masking, RBAC tagging)"
    )


class FrameworkBatchOutput(BaseModel):
    """The structured schema returned by the LLM for a framework."""
    framework_code: str = Field(description="Code of the framework evaluated (e.g., HIPAA, GDPR)")
    evaluations: list[ColumnComplianceFinding] = Field(
        description="List of compliance findings for all in-scope columns"
    )


class FrameworkMetrics(BaseModel):
    score: int | None
    risk_band: RiskBand
    assessment_status: AssessmentStatus = (
        AssessmentStatus.ASSESSED
    )
    total_in_scope: int
    critical_count: int
    serious_count: int
    needs_review_count: int
    good_count: int = 0


class FrameworkAssessmentResult(BaseModel):
    framework_code: str
    metrics: FrameworkMetrics
    findings: list[ColumnComplianceFinding]


class RemediateFindingRequest(BaseModel):
    table_name: str = Field(min_length=1)
    column_name: str = Field(min_length=1)
    remediation_action: str = Field(min_length=1, max_length=64)
    remediated_by: str | None = Field(default=None, max_length=128)
    remediation_notes: str | None = None


class RemediatedFrameworkSummary(BaseModel):
    framework_code: str
    finding_id: int
    original_status: str
    is_remediated: bool = True
    remediation_action: str
    remediated_by: str | None = None
    remediated_at: str | None = None
    updated_metrics: FrameworkMetrics


class RemediateFindingResponse(BaseModel):
    discovery_run_id: str
    table_name: str
    column_name: str
    remediated_findings_count: int
    frameworks_updated: list[RemediatedFrameworkSummary]
