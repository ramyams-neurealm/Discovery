BEGIN;

DROP TABLE IF EXISTS demooc28.compliance_findings CASCADE;
DROP TABLE IF EXISTS demooc28.compliance_assessments CASCADE;

CREATE TABLE IF NOT EXISTS demooc28.compliance_assessments (
    assessment_id SERIAL PRIMARY KEY,
    discovery_run_id VARCHAR(64) NOT NULL,
    framework_code VARCHAR(32) NOT NULL,
    compliance_score INT NOT NULL,
    risk_band VARCHAR(32) NOT NULL,
    in_scope_count INT NOT NULL,
    critical_count INT NOT NULL,
    serious_count INT NOT NULL,
    needs_review_count INT NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    CONSTRAINT uq_run_framework UNIQUE (discovery_run_id, framework_code)
);

CREATE TABLE IF NOT EXISTS demooc28.compliance_findings (
    finding_id SERIAL PRIMARY KEY,
    assessment_id INT REFERENCES demooc28.compliance_assessments(assessment_id) ON DELETE CASCADE,
    table_name VARCHAR(128) NOT NULL,
    column_name VARCHAR(128) NOT NULL,
    status VARCHAR(32) NOT NULL,
    finding_text TEXT NOT NULL,
    recommendation_text TEXT NOT NULL,
    needs_human_review BOOLEAN DEFAULT FALSE,
    is_remediated BOOLEAN DEFAULT FALSE,
    remediation_action VARCHAR(64) NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX idx_comp_assessments_run ON demooc28.compliance_assessments(discovery_run_id);
CREATE INDEX idx_comp_findings_assessment ON demooc28.compliance_findings(assessment_id);

COMMIT;