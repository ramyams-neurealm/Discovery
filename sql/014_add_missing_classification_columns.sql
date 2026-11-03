ALTER TABLE demooc28.column_classifications
    ADD COLUMN IF NOT EXISTS sensitive_data_type VARCHAR(128),
    ADD COLUMN IF NOT EXISTS sensitivity_level VARCHAR(32),
    ADD COLUMN IF NOT EXISTS reason TEXT,
    ADD COLUMN IF NOT EXISTS inference_basis JSONB NOT NULL DEFAULT '[]'::jsonb,
    ADD COLUMN IF NOT EXISTS review_reason TEXT;