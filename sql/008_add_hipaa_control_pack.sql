BEGIN;
CREATE TABLE IF NOT EXISTS demooc28.framework_controls (
    control_id BIGSERIAL PRIMARY KEY,
    policy_pack_version_id BIGINT NOT NULL REFERENCES demooc28.policy_pack_versions(policy_pack_version_id) ON DELETE CASCADE,
    control_code VARCHAR(128) NOT NULL,
    control_title VARCHAR(255) NOT NULL,
    control_description TEXT NOT NULL,
    evidence_type VARCHAR(64) NOT NULL,
    evaluation_type VARCHAR(64) NOT NULL,
    weight NUMERIC(7,4) NOT NULL DEFAULT 1 CHECK (weight > 0),
    default_severity VARCHAR(32) NOT NULL DEFAULT 'NEEDS_REVIEW',
    recommendation_template TEXT NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    control_metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (policy_pack_version_id, control_code)
);
INSERT INTO demooc28.framework_controls (
    policy_pack_version_id, control_code, control_title, control_description,
    evidence_type, evaluation_type, weight, default_severity, recommendation_template
)
SELECT p.policy_pack_version_id, v.control_code, v.title, v.description,
       v.evidence_type, v.evaluation_type, 1, 'NEEDS_REVIEW', v.recommendation
FROM demooc28.compliance_frameworks f
JOIN demooc28.policy_pack_versions p ON p.framework_id=f.framework_id AND p.status='ACTIVE'
CROSS JOIN (VALUES
 ('HIPAA-DATA-001','Identify electronic protected health information','Identify person-linked electronic health information.','COLUMN_CLASSIFICATION','PHI_DISCOVERY','Review and confirm the identified PHI inventory.'),
 ('HIPAA-ACCESS-001','Verify access controls','Verify that access to PHI is restricted.','DATABASE_PERMISSIONS','EVIDENCE_REQUIRED','Obtain and review database permission evidence.'),
 ('HIPAA-AUDIT-001','Verify audit controls','Verify that activity involving PHI is recorded.','AUDIT_CONFIGURATION','EVIDENCE_REQUIRED','Obtain and review audit configuration evidence.'),
 ('HIPAA-INTEGRITY-001','Verify integrity protection','Verify protection from improper alteration or destruction.','INTEGRITY_CONFIGURATION','EVIDENCE_REQUIRED','Obtain and review integrity evidence.'),
 ('HIPAA-TRANS-001','Verify transmission security','Verify protection of PHI during transmission.','TRANSMISSION_SECURITY','EVIDENCE_REQUIRED','Obtain and review transmission-security evidence.'),
 ('HIPAA-REVIEW-001','Verify periodic security review','Verify periodic review of security risks and safeguards.','SECURITY_REVIEW_RECORD','EVIDENCE_REQUIRED','Obtain and review the latest security assessment record.')
) v(control_code,title,description,evidence_type,evaluation_type,recommendation)
WHERE f.framework_code='HIPAA'
ON CONFLICT (policy_pack_version_id, control_code) DO UPDATE SET
 control_title=EXCLUDED.control_title, control_description=EXCLUDED.control_description,
 evidence_type=EXCLUDED.evidence_type, evaluation_type=EXCLUDED.evaluation_type,
 recommendation_template=EXCLUDED.recommendation_template, is_active=TRUE;
CREATE INDEX IF NOT EXISTS idx_framework_controls_policy ON demooc28.framework_controls(policy_pack_version_id,is_active);
DROP TRIGGER IF EXISTS trg_framework_controls_updated_at ON demooc28.framework_controls;
CREATE TRIGGER trg_framework_controls_updated_at BEFORE UPDATE ON demooc28.framework_controls
FOR EACH ROW EXECUTE FUNCTION demooc28.set_updated_at();
COMMIT;
