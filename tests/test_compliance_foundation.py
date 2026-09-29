from datetime import date, datetime, timezone

import pytest
from pydantic import ValidationError

from src.models.compliance_foundation import (
    ClientPolicyInput,
    EvidenceCategory,
    EvidenceCollectionStatus,
    EvidenceSourceType,
    NormalizedEvidence,
    PolicyEffect,
    PolicyScopeType,
    PolicyType,
    PrincipalSelectorType,
)


def test_normalized_evidence_accepts_database_permission():
    evidence = NormalizedEvidence(
        tenant_id=1,
        connection_id=7,
        discovery_run_id="run-123",
        evidence_category=EvidenceCategory.DATABASE_PERMISSIONS,
        evidence_type="DATABASE_PERMISSION",
        source_type=EvidenceSourceType.DATABASE,
        source_system="MYSQL",
        collector_name="mysql_permission_collector",
        collector_version="1.0",
        collection_status=EvidenceCollectionStatus.COLLECTED,
        observation={"privilege": "SELECT"},
        collected_at=datetime.now(timezone.utc),
    )

    assert evidence.source_system == "MYSQL"
    assert evidence.observation["privilege"] == "SELECT"


def test_collected_evidence_rejects_error_payload():
    with pytest.raises(ValidationError):
        NormalizedEvidence(
            tenant_id=1,
            evidence_category=EvidenceCategory.DATABASE_PERMISSIONS,
            evidence_type="DATABASE_PERMISSION",
            source_type=EvidenceSourceType.DATABASE,
            source_system="MYSQL",
            collector_name="mysql_permission_collector",
            collector_version="1.0",
            collection_status=EvidenceCollectionStatus.COLLECTED,
            error={"message": "access denied"},
        )


def test_classification_policy_is_valid_without_connection():
    policy = ClientPolicyInput(
        tenant_id=1,
        policy_code="phi access",
        policy_name="PHI Access Policy",
        policy_type=PolicyType.DATA_ACCESS,
        classification="PHI",
        scope_type=PolicyScopeType.CLASSIFICATION,
        principal_selector_type=(
            PrincipalSelectorType.CLIENT_PRINCIPAL_GROUP
        ),
        principal_selector_value="clinical_roles",
        effect=PolicyEffect.ALLOW,
        allowed_privileges=["select", "SELECT", "update"],
    )

    assert policy.policy_code == "PHI_ACCESS"
    assert policy.allowed_privileges == ["SELECT", "UPDATE"]


def test_table_policy_requires_table_scope_fields():
    with pytest.raises(ValidationError):
        ClientPolicyInput(
            tenant_id=1,
            policy_code="CLAIMS_ACCESS",
            policy_name="Claims access",
            policy_type=PolicyType.DATA_ACCESS,
            scope_type=PolicyScopeType.TABLE,
            connection_id=7,
            principal_selector_type=(
                PrincipalSelectorType.DATABASE_ROLE
            ),
            principal_selector_value="claims_processor",
            effect=PolicyEffect.ALLOW,
            allowed_privileges=["SELECT"],
        )


def test_policy_rejects_invalid_effective_dates():
    with pytest.raises(ValidationError):
        ClientPolicyInput(
            tenant_id=1,
            policy_code="PHI_ACCESS",
            policy_name="PHI Access Policy",
            policy_type=PolicyType.DATA_ACCESS,
            classification="PHI",
            scope_type=PolicyScopeType.CLASSIFICATION,
            principal_selector_type=(
                PrincipalSelectorType.ALL_PRINCIPALS
            ),
            principal_selector_value="*",
            effect=PolicyEffect.DENY,
            effective_from=date(2026, 9, 28),
            effective_to=date(2026, 9, 27),
        )
