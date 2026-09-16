BEGIN;

CREATE TABLE IF NOT EXISTS demooc28.compliance_control_evidence (
    control_evidence_id BIGSERIAL PRIMARY KEY,
    assessment_id BIGINT NOT NULL
        REFERENCES demooc28.compliance_assessments(assessment_id)
        ON DELETE CASCADE,
    control_result_id BIGINT NOT NULL
        REFERENCES demooc28.compliance_control_results(control_result_id)
        ON DELETE CASCADE,
    evidence_source VARCHAR(32) NOT NULL DEFAULT 'USER_ATTESTATION',
    verification_status VARCHAR(32) NOT NULL,
    verification_date DATE,
    explanation TEXT NOT NULL,
    internal_reference VARCHAR(255),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (control_result_id),
    CHECK (evidence_source IN ('USER_ATTESTATION', 'AUTOMATIC')),
    CHECK (verification_status IN ('CONFIRMED', 'NOT_CONFIRMED', 'NOT_SURE')),
    CHECK (length(btrim(explanation)) > 0)
);

CREATE INDEX IF NOT EXISTS idx_control_evidence_assessment
    ON demooc28.compliance_control_evidence(assessment_id);

DROP TRIGGER IF EXISTS trg_compliance_control_evidence_updated_at
    ON demooc28.compliance_control_evidence;
CREATE TRIGGER trg_compliance_control_evidence_updated_at
BEFORE UPDATE ON demooc28.compliance_control_evidence
FOR EACH ROW EXECUTE FUNCTION demooc28.set_updated_at();

COMMIT;
