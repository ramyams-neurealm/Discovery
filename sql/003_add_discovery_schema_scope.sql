BEGIN;

ALTER TABLE demooc28.datasource_connections
    ADD COLUMN IF NOT EXISTS schema_name VARCHAR(255);

COMMIT;