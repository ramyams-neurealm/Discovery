BEGIN;

-- Initial internal PCI DSS database-assessment pack.
-- This is not a complete PCI DSS validation checklist or certification.
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
        'standard_version', 'PCI DSS v4.0.1',
        'scope', 'DATABASE_ASSESSMENT_MVP'
    )
FROM demooc28.compliance_frameworks AS framework
JOIN demooc28.policy_pack_versions AS policy
  ON policy.framework_id = framework.framework_id
 AND policy.status = 'ACTIVE'
CROSS JOIN (
    VALUES
    (
        'PCI-DATA-001',
        'Identify stored payment-card data',
        'Identify columns containing payment-card data that may place the database in PCI DSS scope.',
        'COLUMN_CLASSIFICATION',
        'CARD_DATA_DISCOVERY',
        'Review and confirm the payment-card data inventory and scope.'
    ),
    (
        'PCI-STORAGE-001',
        'Verify protection of stored account data',
        'Verify that stored payment-card data is protected using appropriate storage and cryptographic controls.',
        'STORAGE_PROTECTION',
        'EVIDENCE_REQUIRED',
        'Obtain and review encryption, masking, truncation, tokenization, and key-management evidence.'
    ),
    (
        'PCI-ACCESS-001',
        'Verify access restrictions',
        'Verify that access to payment-card data is restricted according to business need.',
        'DATABASE_PERMISSIONS',
        'EVIDENCE_REQUIRED',
        'Obtain and review database users, roles, permissions, and approved-access evidence.'
    ),
    (
        'PCI-TRANS-001',
        'Verify transmission protection',
        'Verify that payment-card data is protected during transmission.',
        'TRANSMISSION_SECURITY',
        'EVIDENCE_REQUIRED',
        'Obtain and review TLS, certificate, and encrypted-connection evidence.'
    ),
    (
        'PCI-AUDIT-001',
        'Verify logging and monitoring',
        'Verify that access to payment-card data and relevant system activity are logged and reviewed.',
        'AUDIT_CONFIGURATION',
        'EVIDENCE_REQUIRED',
        'Obtain and review audit configuration, log retention, monitoring, and review evidence.'
    ),
    (
        'PCI-VULN-001',
        'Verify vulnerability and patch management',
        'Verify that vulnerabilities affecting the cardholder-data environment are identified and remediated.',
        'VULNERABILITY_MANAGEMENT',
        'EVIDENCE_REQUIRED',
        'Obtain and review vulnerability scans, patch status, and remediation records.'
    ),
    (
        'PCI-TEST-001',
        'Verify security testing',
        'Verify that security controls protecting the cardholder-data environment are tested periodically.',
        'SECURITY_TEST_RECORD',
        'EVIDENCE_REQUIRED',
        'Obtain and review the latest security-test results and remediation records.'
    )
) AS control(
    control_code,
    control_title,
    control_description,
    evidence_type,
    evaluation_type,
    recommendation_template
)
WHERE framework.framework_code = 'PCI_DSS'
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

-- Do not mark PCI DSS AVAILABLE in this migration yet.
-- Availability will be enabled after shared-workflow integration passes.
COMMIT;
