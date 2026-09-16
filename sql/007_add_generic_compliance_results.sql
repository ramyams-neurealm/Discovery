BEGIN;

CREATE TABLE IF NOT EXISTS demooc28.compliance_assessments (
    assessment_id BIGSERIAL PRIMARY KEY,
    discovery_run_id UUID NOT NULL
        REFERENCES demooc28.discovery_runs(discovery_run_id) ON DELETE CASCADE,
    framework_id BIGINT NOT NULL
        REFERENCES demooc28.compliance_frameworks(framework_id),
    policy_pack_version_id BIGINT NOT NULL
        REFERENCES demooc28.policy_pack_versions(policy_pack_version_id),
    status VARCHAR(32) NOT NULL DEFAULT 'PENDING',
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (discovery_run_id, framework_id, policy_pack_version_id),
    CHECK (status IN ('PENDING','RUNNING','COMPLETED','COMPLETED_WITH_WARNINGS','FAILED','SKIPPED'))
);

CREATE TABLE IF NOT EXISTS demooc28.compliance_control_results (
    control_result_id BIGSERIAL PRIMARY KEY,
    assessment_id BIGINT NOT NULL
        REFERENCES demooc28.compliance_assessments(assessment_id) ON DELETE CASCADE,
    control_code VARCHAR(128) NOT NULL,
    control_title VARCHAR(255) NOT NULL,
    assessment_status VARCHAR(32) NOT NULL,
    severity VARCHAR(32),
    explanation TEXT NOT NULL,
    confidence NUMERIC(5,4),
    needs_human_review BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (assessment_id, control_code),
    CHECK (assessment_status IN ('PASS','FAIL','PARTIAL','INSUFFICIENT_EVIDENCE','MANUAL_REVIEW_REQUIRED','NOT_APPLICABLE','NOT_ASSESSED')),
    CHECK (confidence IS NULL OR confidence BETWEEN 0 AND 1)
);

CREATE TABLE IF NOT EXISTS demooc28.compliance_findings (
    compliance_finding_id BIGSERIAL PRIMARY KEY,
    assessment_id BIGINT NOT NULL
        REFERENCES demooc28.compliance_assessments(assessment_id) ON DELETE CASCADE,
    control_result_id BIGINT
        REFERENCES demooc28.compliance_control_results(control_result_id) ON DELETE SET NULL,
    classification_id BIGINT
        REFERENCES demooc28.column_classifications(classification_id) ON DELETE SET NULL,
    severity VARCHAR(32) NOT NULL,
    assessment_status VARCHAR(32) NOT NULL,
    finding TEXT NOT NULL,
    recommendation TEXT NOT NULL,
    confidence NUMERIC(5,4) NOT NULL CHECK (confidence BETWEEN 0 AND 1),
    needs_human_review BOOLEAN NOT NULL DEFAULT FALSE,
    review_reason TEXT,
    verification_status VARCHAR(32) NOT NULL DEFAULT 'PROVISIONAL',
    source_finding_type VARCHAR(64),
    source_finding_id BIGINT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (assessment_status IN ('PASS','FAIL','PARTIAL','INSUFFICIENT_EVIDENCE','MANUAL_REVIEW_REQUIRED','NOT_APPLICABLE','NOT_ASSESSED'))
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_compliance_finding_source
    ON demooc28.compliance_findings(
        assessment_id,
        source_finding_type,
        source_finding_id
    )
    WHERE source_finding_type IS NOT NULL AND source_finding_id IS NOT NULL;

CREATE TABLE IF NOT EXISTS demooc28.compliance_finding_evidence (
    evidence_id BIGSERIAL PRIMARY KEY,
    compliance_finding_id BIGINT NOT NULL
        REFERENCES demooc28.compliance_findings(compliance_finding_id) ON DELETE CASCADE,
    evidence_type VARCHAR(64) NOT NULL,
    evidence_record_id BIGINT,
    evidence_summary TEXT NOT NULL,
    evidence_metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS demooc28.compliance_scores (
    compliance_score_id BIGSERIAL PRIMARY KEY,
    assessment_id BIGINT NOT NULL UNIQUE
        REFERENCES demooc28.compliance_assessments(assessment_id) ON DELETE CASCADE,
    score NUMERIC(5,2),
    risk_band VARCHAR(32) NOT NULL,
    scoring_method VARCHAR(64) NOT NULL DEFAULT 'INTERNAL_POLICY',
    evidence_coverage NUMERIC(5,2) NOT NULL DEFAULT 0
        CHECK (evidence_coverage BETWEEN 0 AND 100),
    applicable_controls INTEGER NOT NULL DEFAULT 0,
    assessed_controls INTEGER NOT NULL DEFAULT 0,
    status_counts JSONB NOT NULL DEFAULT '{}'::jsonb,
    score_metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    calculated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (score IS NULL OR score BETWEEN 0 AND 100)
);

CREATE INDEX IF NOT EXISTS idx_compliance_assessments_run
    ON demooc28.compliance_assessments(discovery_run_id);
CREATE INDEX IF NOT EXISTS idx_compliance_findings_assessment
    ON demooc28.compliance_findings(assessment_id, severity);
CREATE INDEX IF NOT EXISTS idx_compliance_evidence_finding
    ON demooc28.compliance_finding_evidence(compliance_finding_id);

DROP TRIGGER IF EXISTS trg_compliance_assessments_updated_at ON demooc28.compliance_assessments;
CREATE TRIGGER trg_compliance_assessments_updated_at BEFORE UPDATE ON demooc28.compliance_assessments
FOR EACH ROW EXECUTE FUNCTION demooc28.set_updated_at();
DROP TRIGGER IF EXISTS trg_compliance_control_results_updated_at ON demooc28.compliance_control_results;
CREATE TRIGGER trg_compliance_control_results_updated_at BEFORE UPDATE ON demooc28.compliance_control_results
FOR EACH ROW EXECUTE FUNCTION demooc28.set_updated_at();
DROP TRIGGER IF EXISTS trg_compliance_findings_updated_at ON demooc28.compliance_findings;
CREATE TRIGGER trg_compliance_findings_updated_at BEFORE UPDATE ON demooc28.compliance_findings
FOR EACH ROW EXECUTE FUNCTION demooc28.set_updated_at();
DROP TRIGGER IF EXISTS trg_compliance_scores_updated_at ON demooc28.compliance_scores;
CREATE TRIGGER trg_compliance_scores_updated_at BEFORE UPDATE ON demooc28.compliance_scores
FOR EACH ROW EXECUTE FUNCTION demooc28.set_updated_at();

COMMIT;
