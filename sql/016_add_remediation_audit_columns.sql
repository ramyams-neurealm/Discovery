BEGIN;

ALTER TABLE demooc28.compliance_findings
    ADD COLUMN IF NOT EXISTS remediated_by VARCHAR(128) NULL,
    ADD COLUMN IF NOT EXISTS remediated_at TIMESTAMP WITH TIME ZONE NULL,
    ADD COLUMN IF NOT EXISTS remediation_notes TEXT NULL;

CREATE INDEX IF NOT EXISTS idx_comp_findings_table_col
    ON demooc28.compliance_findings (assessment_id, LOWER(table_name), LOWER(column_name));

COMMIT;
