from __future__ import annotations
from datetime import datetime
from typing import Any
from uuid import UUID
from pydantic import BaseModel, Field, SecretStr
from src.models.enums import DatabaseType, DiscoveryScope, DisplayClassification, HipaaSeverity, RunStatus


class ConnectionInput(BaseModel):
    connection_name: str = Field(min_length=1, max_length=255)
    database_type: DatabaseType
    host: str
    port: int = Field(ge=1, le=65535)
    database_name: str
    username: str
    password: SecretStr
    ssl_enabled: bool = True


class ConnectionSafeResponse(BaseModel):
    connection_id: int
    connection_name: str
    database_type: DatabaseType
    host: str
    port: int
    database_name: str
    username: str
    ssl_enabled: bool
    credential_reference: str
    discovery_status: str


class DiscoveryRunRequest(BaseModel):
    connection_id: int
    scopes: list[DiscoveryScope]


class DiscoveryRunResponse(BaseModel):
    discovery_run_id: UUID
    connection_id: int
    status: RunStatus


class ColumnContext(BaseModel):
    object_id: int
    schema_name: str
    table_name: str
    column_name: str
    data_type: str
    nullable: bool | None = None
    is_primary_key: bool = False
    is_foreign_key: bool = False
    neighboring_columns: list[str] = Field(default_factory=list)
    masked_samples: list[str] = Field(default_factory=list)


class ClassificationResult(BaseModel):
    object_id: int
    schema_name: str
    table_name: str
    column_name: str
    display_classification: DisplayClassification
    sensitive_data_type: str
    sensitivity_level: str
    is_sensitive: bool
    confidence: float = Field(ge=0, le=1)
    reason: str
    inference_basis: list[str]
    needs_human_review: bool
    review_reason: str | None = None


class DependencyEdge(BaseModel):
    source_object: str
    source_object_type: str
    target_object: str
    target_object_type: str
    relationship_type: str
    source_column: str | None = None
    target_column: str | None = None
    evidence_source: str
    confidence: float = Field(ge=0, le=1)


class HipaaFinding(BaseModel):
    classification_result_id: int | None = None
    table_name: str
    column_name: str
    severity: HipaaSeverity
    finding: str
    recommendation: str
    confidence: float = Field(ge=0, le=1)
    needs_human_review: bool
    review_reason: str | None = None
    verification_status: str = "PROVISIONAL"


class HipaaScore(BaseModel):
    score: float = Field(ge=0, le=100)
    risk_band: str
    phi_columns_checked: int
    severity_counts: dict[str, int]
    policy_version: str
