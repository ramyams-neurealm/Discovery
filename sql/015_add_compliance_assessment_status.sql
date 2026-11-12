BEGIN;

ALTER TABLE demooc28.compliance_assessments
    ADD COLUMN IF NOT EXISTS assessment_status VARCHAR(32)
        NOT NULL DEFAULT 'ASSESSED',
    ADD COLUMN IF NOT EXISTS good_count INTEGER
        NOT NULL DEFAULT 0;

ALTER TABLE demooc28.compliance_assessments
    ALTER COLUMN compliance_score DROP NOT NULL;

UPDATE demooc28.compliance_assessments
SET assessment_status = CASE
    WHEN in_scope_count = 0
        THEN 'NO_COLUMNS_IN_SCOPE'
    ELSE 'ASSESSED'
END
WHERE assessment_status = 'ASSESSED';

ALTER TABLE demooc28.compliance_assessments
    DROP CONSTRAINT IF EXISTS chk_compliance_assessment_status;

ALTER TABLE demooc28.compliance_assessments
    ADD CONSTRAINT chk_compliance_assessment_status
    CHECK (
        assessment_status IN (
            'ASSESSED',
            'NO_COLUMNS_IN_SCOPE',
            'EVALUATION_FAILED'
        )
    );

COMMIT;