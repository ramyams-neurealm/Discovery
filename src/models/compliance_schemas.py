from enum import Enum
from typing import Literal
from pydantic import BaseModel, Field


class ComplianceStatus(str, Enum):
    CRITICAL = "Critical"
    SERIOUS = "Serious"
    NEEDS_REVIEW = "Needs review"


class RiskBand(str, Enum):
    GOOD = "GOOD"
    MODERATE_RISK = "MODERATE_RISK"
    SERIOUS_RISK = "SERIOUS_RISK"
    CRITICAL_RISK = "CRITICAL_RISK"


class ColumnComplianceFinding(BaseModel):
    """Evaluation result for a single column under a specific framework."""
    column_name: str = Field(description="Name of the evaluated column")
    status: Literal["Critical", "Serious", "Needs review"] = Field(
        description="Must be strictly Critical, Serious, or Needs review"
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
    score: int
    risk_band: RiskBand
    total_in_scope: int
    critical_count: int
    serious_count: int
    needs_review_count: int


class FrameworkAssessmentResult(BaseModel):
    framework_code: str
    metrics: FrameworkMetrics
    findings: list[ColumnComplianceFinding]