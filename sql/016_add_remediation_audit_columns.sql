BEGIN;

ALTER TABLE demooc28.compliance_findings
    ADD COLUMN IF NOT EXISTS remediation_status VARCHAR(40) NOT NULL DEFAULT 'OPEN',
    ADD COLUMN IF NOT EXISTS remediated_by VARCHAR(128) NULL,
    ADD COLUMN IF NOT EXISTS remediated_at TIMESTAMP WITH TIME ZONE NULL,
    ADD COLUMN IF NOT EXISTS remediation_notes TEXT NULL;

UPDATE demooc28.compliance_findings
SET remediation_status = CASE
    WHEN is_remediated = TRUE THEN 'VERIFIED'
    ELSE 'OPEN'
END
WHERE remediation_status = 'OPEN' AND is_remediated = TRUE;

CREATE INDEX IF NOT EXISTS idx_comp_findings_table_col
    ON demooc28.compliance_findings (assessment_id, LOWER(table_name), LOWER(column_name));

COMMIT;
