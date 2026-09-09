from __future__ import annotations

from datetime import date
from uuid import UUID

from pydantic import (
    BaseModel,
    Field,
    SecretStr,
    field_validator,
    model_validator,
)

from src.models.enums import (
    DatabaseType,
    DiscoveryScope,
    DisplayClassification,
    FrameworkImplementationStatus,
    HipaaSeverity,
    PolicyPackStatus,
    RunStatus,
)


# ============================================================
# Connection models
# ============================================================


class ConnectionInput(BaseModel):
    """Request model used to test and save a database connection."""

    connection_name: str = Field(
        min_length=1,
        max_length=255,
    )
    database_type: DatabaseType
    host: str = Field(
        min_length=1,
        max_length=255,
    )
    port: int = Field(
        ge=1,
        le=65535,
    )
    database_name: str = Field(
        min_length=1,
        max_length=255,
    )
    schema_name: str | None = Field(
        default=None,
        max_length=255,
    )
    username: str = Field(
        min_length=1,
        max_length=255,
    )
    password: SecretStr
    ssl_enabled: bool = True

    @field_validator(
        "connection_name",
        "host",
        "database_name",
        "username",
        mode="before",
    )
    @classmethod
    def strip_required_text(
        cls,
        value: str,
    ) -> str:
        if not isinstance(value, str):
            return value

        cleaned_value = value.strip()

        if not cleaned_value:
            raise ValueError(
                "Value must not be blank"
            )

        return cleaned_value

    @field_validator(
        "schema_name",
        mode="before",
    )
    @classmethod
    def strip_optional_schema_name(
        cls,
        value: str | None,
    ) -> str | None:
        if value is None:
            return None

        if not isinstance(value, str):
            return value

        cleaned_value = value.strip()

        return cleaned_value or None

class ConnectionUpdate(BaseModel):
    """Optional fields used to update a saved database connection."""

    connection_name: str | None = Field(
        default=None,
        min_length=1,
        max_length=255,
    )
    host: str | None = Field(
        default=None,
        min_length=1,
        max_length=255,
    )
    port: int | None = Field(
        default=None,
        ge=1,
        le=65535,
    )
    database_name: str | None = Field(
        default=None,
        min_length=1,
        max_length=255,
    )
    schema_name: str | None = Field(
        default=None,
        max_length=255,
    )
    username: str | None = Field(
        default=None,
        min_length=1,
        max_length=255,
    )
    password: SecretStr | None = None
    ssl_enabled: bool | None = None

    @field_validator(
        "connection_name",
        "host",
        "database_name",
        "username",
        mode="before",
    )
    @classmethod
    def strip_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None

        if not isinstance(value, str):
            return value

        cleaned_value = value.strip()

        if not cleaned_value:
            raise ValueError("Value must not be blank")

        return cleaned_value
    @field_validator(
        "schema_name",
        mode="before",
    )
    @classmethod
    def strip_optional_schema_name(
        cls,
        value: str | None,
    ) -> str | None:
        if value is None:
            return None

        if not isinstance(value, str):
            return value

        return value.strip() or None


class ConnectionSafeResponse(BaseModel):
    """Safe datasource response returned to the frontend."""

    connection_id: int
    connection_name: str
    database_type: DatabaseType
    host: str
    port: int
    database_name: str
    schema_name: str | None = None
    username: str
    ssl_enabled: bool
    is_active: bool = True
    discovery_status: str


# ============================================================
# Compliance framework catalog models
# ============================================================
class PolicyPackVersionResponse(BaseModel):
    version: str
    status: PolicyPackStatus
    scoring_enabled: bool
    effective_from: date | None = None
    effective_to: date | None = None


class ComplianceFrameworkResponse(BaseModel):
    framework_code: str
    framework_name: str
    description: str | None = None
    region: str | None = None
    implementation_status: FrameworkImplementationStatus
    is_active: bool
    policy_pack: PolicyPackVersionResponse | None = None


class ComplianceFrameworkListResponse(BaseModel):
    framework_count: int = Field(ge=0)
    frameworks: list[ComplianceFrameworkResponse] = Field(default_factory=list)


# ============================================================
# Discovery run models
# ============================================================


class SelectedDiscoveryObject(BaseModel):
    """One database object selected for a scoped discovery run."""

    object_name: str = Field(
        min_length=1,
        max_length=255,
    )
    object_type: str = Field(
        min_length=1,
        max_length=64,
    )

    @field_validator(
        "object_name",
        mode="before",
    )
    @classmethod
    def strip_object_name(cls, value: str) -> str:
        if not isinstance(value, str):
            return value

        cleaned_value = value.strip()

        if not cleaned_value:
            raise ValueError("Object name must not be blank")

        return cleaned_value

    @field_validator(
        "object_type",
        mode="before",
    )
    @classmethod
    def normalize_object_type(cls, value: str) -> str:
        if not isinstance(value, str):
            return value

        normalized = value.strip().upper().replace(" ", "_")
        allowed_types = {
            "TABLE",
            "VIEW",
            "MATERIALIZED_VIEW",
            "PROCEDURE",
            "FUNCTION",
            "TRIGGER",
        }

        if normalized not in allowed_types:
            raise ValueError(
                "Unsupported object type. Expected one of: "
                + ", ".join(sorted(allowed_types))
            )

        return normalized




class DiscoveryRunRequest(BaseModel):
    """Request used to start a Discovery run."""

    connection_id: int = Field(gt=0)
    scopes: list[DiscoveryScope] = Field(min_length=1)
    selected_objects: list[SelectedDiscoveryObject] = Field(
        default_factory=list,
        max_length=500,
    )
    selected_frameworks: list[str] = Field(
        default_factory=list,
        max_length=50,
    )

    @field_validator("scopes")
    @classmethod
    def remove_duplicate_scopes(
        cls,
        scopes: list[DiscoveryScope],
    ) -> list[DiscoveryScope]:
        return list(dict.fromkeys(scopes))

    @field_validator("selected_frameworks", mode="before")
    @classmethod
    def normalize_selected_frameworks(
        cls,
        frameworks: list[str] | None,
    ) -> list[str]:
        normalized: list[str] = []
        seen: set[str] = set()
        for framework in frameworks or []:
            if not isinstance(framework, str):
                raise ValueError("Framework codes must be strings")
            code = framework.strip().upper().replace("/", "_").replace(" ", "_")
            if not code:
                raise ValueError("Framework code must not be blank")
            if code not in seen:
                seen.add(code)
                normalized.append(code)
        return normalized

    @model_validator(mode="after")
    def validate_compliance_framework_selection(
        self,
    ) -> DiscoveryRunRequest:
        if (
            DiscoveryScope.REGULATORY_COMPLIANCE in self.scopes
            and not self.selected_frameworks
        ):
            raise ValueError(
                "selected_frameworks is required when "
                "REGULATORY_COMPLIANCE is requested"
            )
        return self

    @field_validator("selected_objects")
    @classmethod
    def remove_duplicate_objects(
        cls,
        selected_objects: list[SelectedDiscoveryObject],
    ) -> list[SelectedDiscoveryObject]:
        unique_objects: list[SelectedDiscoveryObject] = []
        seen: set[tuple[str, str]] = set()

        for selected_object in selected_objects:
            key = (
                selected_object.object_type,
                selected_object.object_name,
            )

            if key in seen:
                continue

            seen.add(key)
            unique_objects.append(selected_object)

        return unique_objects
    


class DiscoveryRunResponse(BaseModel):
    """Response returned after a Discovery run is accepted."""

    discovery_run_id: UUID
    connection_id: int
    status: RunStatus
    requested_scopes: list[DiscoveryScope] = Field(default_factory=list)
    effective_scopes: list[DiscoveryScope] = Field(default_factory=list)
    selected_frameworks: list[str] = Field(default_factory=list)


# ============================================================
# Classification models
# ============================================================


class ColumnContext(BaseModel):
    """Metadata and masked profiling evidence for classification."""

    object_id: int = Field(gt=0)
    column_id: int | None = Field(default=None, gt=0)
    schema_name: str
    table_name: str
    column_name: str
    data_type: str
    nullable: bool | None = None
    is_primary_key: bool = False
    is_foreign_key: bool = False
    neighboring_columns: list[str] = Field(default_factory=list)
    masked_samples: list[str] = Field(default_factory=list, max_length=3)
    null_percentage: float | None = Field(default=None, ge=0, le=100)
    distinct_count: int | None = Field(default=None, ge=0)
    table_row_count: int | None = Field(default=None, ge=0)


class ClassificationResult(BaseModel):
    """Structured result returned by the classification agent."""

    object_id: int = Field(gt=0)
    schema_name: str
    table_name: str
    column_name: str
    display_classification: DisplayClassification
    sensitive_data_type: str = Field(min_length=1, max_length=128)
    sensitivity_level: str
    is_sensitive: bool
    confidence: float = Field(ge=0, le=1)
    reason: str = Field(min_length=1)
    inference_basis: list[str] = Field(default_factory=list)
    needs_human_review: bool
    review_reason: str | None = None

    @model_validator(mode="after")
    def ensure_review_reason(self) -> ClassificationResult:
        if self.needs_human_review and not self.review_reason:
            self.review_reason = "Human review is required."

        return self


# ============================================================
# Dependency models
# ============================================================


class DependencyEdge(BaseModel):
    """Direct relationship between two discovered database objects."""

    source_object: str
    source_object_type: str
    target_object: str
    target_object_type: str
    relationship_type: str
    source_column: str | None = None
    target_column: str | None = None
    evidence_source: str
    confidence: float = Field(ge=0, le=1)


# ============================================================
# HIPAA models
# ============================================================


class HipaaFinding(BaseModel):
    """Structured HIPAA finding for one PHI classification."""

    classification_result_id: int | None = None
    table_name: str
    column_name: str
    severity: HipaaSeverity
    finding: str = Field(min_length=1)
    recommendation: str = Field(min_length=1)
    confidence: float = Field(ge=0, le=1)
    needs_human_review: bool
    review_reason: str | None = None
    verification_status: str = "PROVISIONAL"

    @model_validator(mode="after")
    def ensure_review_reason(self) -> HipaaFinding:
        if self.needs_human_review and not self.review_reason:
            self.review_reason = "Human review is required."

        return self


class HipaaScore(BaseModel):
    """Deterministically calculated HIPAA score."""

    score: float = Field(ge=0, le=100)
    risk_band: str
    phi_columns_checked: int = Field(ge=0)
    severity_counts: dict[str, int]
    policy_version: str

    @field_validator("severity_counts")
    @classmethod
    def validate_severity_counts(
        cls,
        severity_counts: dict[str, int],
    ) -> dict[str, int]:
        if any(count < 0 for count in severity_counts.values()):
            raise ValueError("Severity counts must not be negative")

        return severity_counts
