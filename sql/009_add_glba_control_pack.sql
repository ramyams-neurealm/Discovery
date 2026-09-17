BEGIN;

-- Initial internal GLBA database-assessment pack.
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
    1.0, -- Equal weight of 1
    'NEEDS_REVIEW',
    control.recommendation_template,
    jsonb_build_object(
        'internal_control', true,
        'standard_version', 'GLBA Safeguards Rule',
        'scope', 'DATABASE_ASSESSMENT_MVP'
    )
FROM demooc28.compliance_frameworks AS framework
JOIN demooc28.policy_pack_versions AS policy
  ON policy.framework_id = framework.framework_id
 AND policy.status = 'PLANNED' -- Keep GLBA PLANNED until reviewed
CROSS JOIN (
    VALUES
    (
        'GLBA-DATA-001',
        'Identify stored financial data',
        'Identify columns containing nonpublic personal information like bank accounts.',
        'COLUMN_CLASSIFICATION',
        'FINANCIAL_DATA_DISCOVERY',
        'Review and confirm the financial data inventory and scope.'
    ),
    (
        'GLBA-STORAGE-001',
        'Verify protection of stored financial data',
        'Verify that stored financial data is protected using appropriate encryption at rest.',
        'STORAGE_PROTECTION',
        'EVIDENCE_REQUIRED',
        'Obtain and review encryption and key-management evidence.'
    ),
    (
        'GLBA-ACCESS-001',
        'Verify access restrictions',
        'Verify that access to financial data is restricted according to business need.',
        'DATABASE_PERMISSIONS',
        'EVIDENCE_REQUIRED',
        'Obtain and review database users, roles, permissions, and approved-access evidence.'
    ),
    (
        'GLBA-TRANS-001',
        'Verify transmission protection',
        'Verify that financial data is protected during transmission using TLS/SSL.',
        'TRANSMISSION_SECURITY',
        'EVIDENCE_REQUIRED',
        'Obtain and review TLS, certificate, and encrypted-connection evidence.'
    ),
    (
        'GLBA-AUDIT-001',
        'Verify logging and monitoring',
        'Verify that access to financial data and relevant system activity are logged and reviewed.',
        'AUDIT_CONFIGURATION',
        'EVIDENCE_REQUIRED',
        'Obtain and review audit configuration, log retention, monitoring, and review evidence.'
    ),
    (
        'GLBA-REVIEW-001',
        'Verify periodic safeguards review',
        'Verify periodic internal testing and review of administrative and technical safeguards.',
        'SECURITY_TEST_RECORD',
        'EVIDENCE_REQUIRED',
        'Obtain and review the latest security-test results and compliance attestation records.'
    )
) AS control(
    control_code,
    control_title,
    control_description,
    evidence_type,
    evaluation_type,
    recommendation_template
)
WHERE framework.framework_code = 'GLBA'
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