BEGIN;

-- Initial internal GDPR database-assessment pack.
INSERT INTO demooc28.framework_controls (
    policy_pack_version_id,
    control_code,
    control_title,
    control_description,
    evidence_type,
    evaluation_type,
    weight,
    default_severity,
    recommendation_template,
    control_metadata
)
SELECT
    policy.policy_pack_version_id,
    control.control_code,
    control.control_title,
    control.control_description,
    control.evidence_type,
    control.evaluation_type,
    1.0,
    'NEEDS_REVIEW',
    control.recommendation_template,
    jsonb_build_object(
        'internal_control', true,
        'standard_version', 'GDPR v1.0',
        'scope', 'DATABASE_ASSESSMENT_MVP'
    )
FROM demooc28.compliance_frameworks AS framework
JOIN demooc28.policy_pack_versions AS policy
  ON policy.framework_id = framework.framework_id
 AND policy.status = 'PLANNED'
CROSS JOIN (
    VALUES
    (
        'GDPR-DATA-001',
        'Identify stored personal data (PII)',
        'Identify columns containing Personally Identifiable Information (PII) that places the database in GDPR scope.',
        'COLUMN_CLASSIFICATION',
        'PII_DISCOVERY',
        'Review and confirm the personal data inventory and scope.'
    ),
    (
        'GDPR-STORAGE-001',
        'Verify protection of stored personal data',
        'Verify that stored personal data is protected using encryption or pseudonymization at rest.',
        'STORAGE_PROTECTION',
        'EVIDENCE_REQUIRED',
        'Obtain and review encryption, masking, and pseudonymization evidence.'
    ),
    (
        'GDPR-ACCESS-001',
        'Verify access restrictions',
        'Verify that access to personal data is restricted to authorized personnel (Least Privilege).',
        'DATABASE_PERMISSIONS',
        'EVIDENCE_REQUIRED',
        'Obtain and review database users, roles, and approved-access evidence.'
    ),
    (
        'GDPR-ERASURE-001',
        'Verify data deletion capabilities',
        'Verify mechanisms exist to support the Right to Erasure (Right to be Forgotten) for personal data.',
        'RETENTION_POLICY',
        'EVIDENCE_REQUIRED',
        'Obtain and review data retention policies and automated deletion scripts.'
    ),
    (
        'GDPR-TRANS-001',
        'Verify transmission protection',
        'Verify that personal data is protected during transmission using TLS/SSL.',
        'TRANSMISSION_SECURITY',
        'EVIDENCE_REQUIRED',
        'Obtain and review TLS, certificate, and encrypted-connection evidence.'
    ),
    (
        'GDPR-AUDIT-001',
        'Verify logging and monitoring',
        'Verify that access to personal data is logged for security auditing.',
        'AUDIT_CONFIGURATION',
        'EVIDENCE_REQUIRED',
        'Obtain and review audit configuration and log retention evidence.'
    )
) AS control(
    control_code,
    control_title,
    control_description,
    evidence_type,
    evaluation_type,
    recommendation_template
)
WHERE framework.framework_code = 'GDPR'
ON CONFLICT (policy_pack_version_id, control_code) DO UPDATE SET
    control_title = EXCLUDED.control_title,
    control_description = EXCLUDED.control_description,
    evidence_type = EXCLUDED.evidence_type,
    evaluation_type = EXCLUDED.evaluation_type,
    weight = EXCLUDED.weight,
    default_severity = EXCLUDED.default_severity,
    recommendation_template = EXCLUDED.recommendation_template,
    control_metadata = EXCLUDED.control_metadata,
    is_active = TRUE;

COMMIT;