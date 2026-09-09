BEGIN;

ALTER TABLE demooc28.discovery_runs
    ADD COLUMN IF NOT EXISTS selected_frameworks JSONB
    NOT NULL DEFAULT '[]'::jsonb;

ALTER TABLE demooc28.discovery_runs
    DROP CONSTRAINT IF EXISTS ck_discovery_runs_selected_frameworks_array;

ALTER TABLE demooc28.discovery_runs
    ADD CONSTRAINT ck_discovery_runs_selected_frameworks_array
    CHECK (jsonb_typeof(selected_frameworks) = 'array');

CREATE INDEX IF NOT EXISTS idx_discovery_runs_selected_frameworks
    ON demooc28.discovery_runs
    USING GIN (selected_frameworks);

-- Permit the generic compliance stage in discovery_runs.current_stage.
ALTER TABLE demooc28.discovery_runs
    DROP CONSTRAINT IF EXISTS ck_discovery_current_stage;

ALTER TABLE demooc28.discovery_runs
    ADD CONSTRAINT ck_discovery_current_stage
    CHECK (
        current_stage IS NULL
        OR current_stage IN (
            'CONNECTION_VALIDATION',
            'METADATA_PROFILING',
            'COLUMN_CLASSIFICATION',
            'DEPENDENCY_MAPPING',
            'REGULATORY_COMPLIANCE',
            'HIPAA_COMPLIANCE',
            'REPORT_FINALIZATION'
        )
    );

-- Permit the same stage in discovery_run_stages.stage_name.
ALTER TABLE demooc28.discovery_run_stages
    DROP CONSTRAINT IF EXISTS ck_discovery_stage_name;

ALTER TABLE demooc28.discovery_run_stages
    ADD CONSTRAINT ck_discovery_stage_name
    CHECK (
        stage_name IN (
            'CONNECTION_VALIDATION',
            'METADATA_PROFILING',
            'COLUMN_CLASSIFICATION',
            'DEPENDENCY_MAPPING',
            'REGULATORY_COMPLIANCE',
            'HIPAA_COMPLIANCE',
            'REPORT_FINALIZATION'
        )
    );

COMMIT;
