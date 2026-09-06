BEGIN;

ALTER TABLE demooc28.discovery_runs
    ADD COLUMN IF NOT EXISTS selected_objects JSONB
    NOT NULL DEFAULT '[]'::jsonb;

COMMIT;