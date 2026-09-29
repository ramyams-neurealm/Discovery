from __future__ import annotations

from datetime import UTC, date, datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator


class EvidenceCategory(str, Enum):
    COLUMN_CLASSIFICATION = "COLUMN_CLASSIFICATION"
    DATABASE_PERMISSIONS = "DATABASE_PERMISSIONS"
    TRANSMISSION_SECURITY = "TRANSMISSION_SECURITY"
    STORAGE_PROTECTION = "STORAGE_PROTECTION"
    AUDIT_CONFIGURATION = "AUDIT_CONFIGURATION"
    AUDIT_ACTIVITY = "AUDIT_ACTIVITY"
    INTEGRITY_CONFIGURATION = "INTEGRITY_CONFIGURATION"
    MASKING_CONFIGURATION = "MASKING_CONFIGURATION"
    RETENTION_POLICY = "RETENTION_POLICY"
    DELETION_CAPABILITY = "DELETION_CAPABILITY"
    VULNERABILITY_MANAGEMENT = "VULNERABILITY_MANAGEMENT"
    SECURITY_TEST_RECORD = "SECURITY_TEST_RECORD"
    SECURITY_REVIEW_RECORD = "SECURITY_REVIEW_RECORD"
    IDENTITY_CONFIGURATION = "IDENTITY_CONFIGURATION"
    NETWORK_CONFIGURATION = "NETWORK_CONFIGURATION"


class EvidenceSourceType(str, Enum):
    DATABASE = "DATABASE"
    CLOUD = "CLOUD"
    IDENTITY_PROVIDER = "IDENTITY_PROVIDER"
    MANUAL = "MANUAL"
    APPLICATION = "APPLICATION"


class EvidenceCollectionStatus(str, Enum):
    COLLECTED = "COLLECTED"
    PARTIALLY_COLLECTED = "PARTIALLY_COLLECTED"
    PERMISSION_DENIED = "PERMISSION_DENIED"
    NOT_SUPPORTED = "NOT_SUPPORTED"
    NOT_CONFIGURED = "NOT_CONFIGURED"
    COLLECTION_FAILED = "COLLECTION_FAILED"


class PrincipalType(str, Enum):
    DATABASE_USER = "DATABASE_USER"
    DATABASE_ROLE = "DATABASE_ROLE"
    IDENTITY_USER = "IDENTITY_USER"
    IDENTITY_GROUP = "IDENTITY_GROUP"
    SERVICE_ACCOUNT = "SERVICE_ACCOUNT"
    SERVICE_PRINCIPAL = "SERVICE_PRINCIPAL"
    PUBLIC = "PUBLIC"


class PolicyType(str, Enum):
    DATA_ACCESS = "DATA_ACCESS"
    DATA_MASKING = "DATA_MASKING"
    DATA_RETENTION = "DATA_RETENTION"
    AUDIT_REQUIREMENT = "AUDIT_REQUIREMENT"
    TRANSMISSION_SECURITY = "TRANSMISSION_SECURITY"
    STORAGE_PROTECTION = "STORAGE_PROTECTION"


class PolicyScopeType(str, Enum):
    TENANT = "TENANT"
    CONNECTION = "CONNECTION"
    CLASSIFICATION = "CLASSIFICATION"
    SCHEMA = "SCHEMA"
    TABLE = "TABLE"
    COLUMN = "COLUMN"


class PrincipalSelectorType(str, Enum):
    EXACT_PRINCIPAL = "EXACT_PRINCIPAL"
    DATABASE_ROLE = "DATABASE_ROLE"
    CLIENT_PRINCIPAL_GROUP = "CLIENT_PRINCIPAL_GROUP"
    IDENTITY_GROUP = "IDENTITY_GROUP"
    SERVICE_ACCOUNT = "SERVICE_ACCOUNT"
    ALL_PRINCIPALS = "ALL_PRINCIPALS"


class PolicyEffect(str, Enum):
    ALLOW = "ALLOW"
    DENY = "DENY"
    ALLOW_WITH_CONDITIONS = "ALLOW_WITH_CONDITIONS"


class PolicyStatus(str, Enum):
    DRAFT = "DRAFT"
    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"
    RETIRED = "RETIRED"


class EvidencePrincipal(BaseModel):
    principal_type: PrincipalType | None = None
    principal_name: str | None = Field(default=None, max_length=512)
    principal_host: str | None = Field(default=None, max_length=255)
    principal_source: str | None = Field(default=None, max_length=64)


class EvidenceResource(BaseModel):
    resource_type: str | None = Field(default=None, max_length=64)
    catalog_name: str | None = Field(default=None, max_length=255)
    schema_name: str | None = Field(default=None, max_length=255)
    table_name: str | None = Field(default=None, max_length=255)
    column_name: str | None = Field(default=None, max_length=255)
    qualified_name: str | None = Field(default=None, max_length=1024)


class NormalizedEvidence(BaseModel):
    tenant_id: int = Field(gt=0)
    connection_id: int | None = Field(default=None, gt=0)
    discovery_run_id: str | None = None

    evidence_category: EvidenceCategory
    evidence_type: str = Field(min_length=1, max_length=64)

    source_type: EvidenceSourceType
    source_system: str = Field(min_length=1, max_length=64)
    collector_name: str = Field(min_length=1, max_length=128)
    collector_version: str = Field(min_length=1, max_length=64)

    principal: EvidencePrincipal = Field(default_factory=EvidencePrincipal)
    resource: EvidenceResource = Field(default_factory=EvidenceResource)
    observation: dict[str, Any] = Field(default_factory=dict)

    collection_status: EvidenceCollectionStatus
    collected_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC)
    )
    valid_until: datetime | None = None
    raw_reference: dict[str, Any] = Field(default_factory=dict)
    error: dict[str, Any] | None = None

    @field_validator(
        "evidence_type",
        "source_system",
        "collector_name",
        "collector_version",
        mode="before",
    )
    @classmethod
    def normalize_required_text(cls, value: str) -> str:
        if not isinstance(value, str):
            return value
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Value must not be blank")
        return cleaned

    @model_validator(mode="after")
    def validate_collection_result(self) -> "NormalizedEvidence":
        if self.valid_until is not None and self.valid_until < self.collected_at:
            raise ValueError("valid_until must not be earlier than collected_at")
        if (
            self.collection_status == EvidenceCollectionStatus.COLLECTED
            and self.error is not None
        ):
            raise ValueError("Collected evidence must not contain an error")
        return self


class ClientPolicyInput(BaseModel):
    tenant_id: int = Field(gt=0)
    policy_code: str = Field(min_length=1, max_length=128)
    policy_name: str = Field(min_length=1, max_length=255)
    policy_type: PolicyType

    classification: str | None = Field(default=None, max_length=64)
    sensitive_data_type: str | None = Field(default=None, max_length=128)

    scope_type: PolicyScopeType
    connection_id: int | None = Field(default=None, gt=0)
    catalog_name: str | None = Field(default=None, max_length=255)
    schema_name: str | None = Field(default=None, max_length=255)
    table_name: str | None = Field(default=None, max_length=255)
    column_name: str | None = Field(default=None, max_length=255)

    principal_selector_type: PrincipalSelectorType
    principal_selector_value: str = Field(min_length=1, max_length=512)

    effect: PolicyEffect
    allowed_privileges: list[str] = Field(default_factory=list)
    conditions: dict[str, Any] = Field(default_factory=dict)
    priority: int = Field(default=100, ge=0, le=1000)

    status: PolicyStatus = PolicyStatus.DRAFT
    effective_from: date | None = None
    effective_to: date | None = None
    approved_by: str | None = Field(default=None, max_length=255)
    approved_at: datetime | None = None
    review_due_at: datetime | None = None

    @field_validator(
        "policy_code",
        "policy_name",
        "principal_selector_value",
        mode="before",
    )
    @classmethod
    def normalize_required_text(cls, value: str) -> str:
        if not isinstance(value, str):
            return value
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Value must not be blank")
        return cleaned

    @field_validator("policy_code", mode="after")
    @classmethod
    def normalize_policy_code(cls, value: str) -> str:
        return value.upper().replace(" ", "_")

    @field_validator("allowed_privileges", mode="before")
    @classmethod
    def normalize_privileges(cls, values: list[str] | None) -> list[str]:
        normalized: list[str] = []
        for value in values or []:
            privilege = str(value).strip().upper()
            if privilege and privilege not in normalized:
                normalized.append(privilege)
        return normalized

    @model_validator(mode="after")
    def validate_scope_and_dates(self) -> "ClientPolicyInput":
        required_by_scope = {
            PolicyScopeType.CONNECTION: ("connection_id",),
            PolicyScopeType.CLASSIFICATION: ("classification",),
            PolicyScopeType.SCHEMA: ("connection_id", "schema_name"),
            PolicyScopeType.TABLE: (
                "connection_id",
                "schema_name",
                "table_name",
            ),
            PolicyScopeType.COLUMN: (
                "connection_id",
                "schema_name",
                "table_name",
                "column_name",
            ),
        }
        missing = [
            field_name
            for field_name in required_by_scope.get(self.scope_type, ())
            if getattr(self, field_name) in (None, "")
        ]
        if missing:
            raise ValueError(
                f"{self.scope_type.value} scope requires: "
                + ", ".join(missing)
            )
        if (
            self.effective_from is not None
            and self.effective_to is not None
            and self.effective_to < self.effective_from
        ):
            raise ValueError("effective_to must not precede effective_from")
        return self


class PrincipalGroupInput(BaseModel):
    tenant_id: int = Field(gt=0)
    group_code: str = Field(min_length=1, max_length=128)
    group_name: str = Field(min_length=1, max_length=255)
    description: str | None = None

    @field_validator("group_code", mode="after")
    @classmethod
    def normalize_group_code(cls, value: str) -> str:
        return value.strip().lower().replace(" ", "_")


class PrincipalGroupMemberInput(BaseModel):
    connection_id: int | None = Field(default=None, gt=0)
    principal_type: PrincipalType
    principal_name: str = Field(min_length=1, max_length=512)
    principal_source: str = Field(default="DATABASE", max_length=64)
