CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE IF NOT EXISTS datasource_connections (
    connection_id BIGSERIAL PRIMARY KEY,
    connection_name VARCHAR(255) NOT NULL,
    database_type VARCHAR(32) NOT NULL,
    host VARCHAR(255) NOT NULL,
    port INTEGER NOT NULL,
    database_name VARCHAR(255) NOT NULL,
    username VARCHAR(255) NOT NULL,
    ssl_enabled BOOLEAN NOT NULL DEFAULT TRUE,
    credential_reference VARCHAR(512) NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    discovery_status VARCHAR(32) NOT NULL DEFAULT 'NOT_STARTED',
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS discovery_runs (
    discovery_run_id UUID PRIMARY KEY,
    connection_id BIGINT NOT NULL REFERENCES datasource_connections(connection_id),
    requested_scopes JSONB NOT NULL,
    effective_scopes JSONB,
    status VARCHAR(32) NOT NULL,
    current_stage VARCHAR(64),
    progress_percentage NUMERIC(5,2) NOT NULL DEFAULT 0,
    error_message TEXT,
    started_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMP,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS discovered_objects (
    object_id BIGSERIAL PRIMARY KEY,
    discovery_run_id UUID NOT NULL REFERENCES discovery_runs(discovery_run_id),
    connection_id BIGINT NOT NULL REFERENCES datasource_connections(connection_id),
    schema_name VARCHAR(255) NOT NULL,
    object_name VARCHAR(255) NOT NULL,
    object_type VARCHAR(64) NOT NULL,
    object_ddl TEXT,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    UNIQUE (discovery_run_id, schema_name, object_name, object_type)
);

CREATE TABLE IF NOT EXISTS discovered_columns (
    column_id BIGSERIAL PRIMARY KEY,
    discovery_run_id UUID NOT NULL REFERENCES discovery_runs(discovery_run_id),
    object_id BIGINT NOT NULL REFERENCES discovered_objects(object_id),
    column_name VARCHAR(255) NOT NULL,
    ordinal_position INTEGER,
    data_type VARCHAR(255) NOT NULL,
    nullable BOOLEAN,
    default_value TEXT,
    is_primary_key BOOLEAN NOT NULL DEFAULT FALSE,
    is_foreign_key BOOLEAN NOT NULL DEFAULT FALSE,
    UNIQUE (discovery_run_id, object_id, column_name)
);

CREATE TABLE IF NOT EXISTS table_profiles (
    table_profile_id BIGSERIAL PRIMARY KEY,
    discovery_run_id UUID NOT NULL REFERENCES discovery_runs(discovery_run_id),
    object_id BIGINT NOT NULL REFERENCES discovered_objects(object_id),
    row_count BIGINT,
    column_count INTEGER NOT NULL,
    average_null_percentage NUMERIC(7,4),
    UNIQUE (discovery_run_id, object_id)
);

CREATE TABLE IF NOT EXISTS column_profiles (
    column_profile_id BIGSERIAL PRIMARY KEY,
    discovery_run_id UUID NOT NULL REFERENCES discovery_runs(discovery_run_id),
    column_id BIGINT NOT NULL REFERENCES discovered_columns(column_id),
    null_percentage NUMERIC(7,4),
    distinct_count BIGINT,
    masked_samples JSONB NOT NULL DEFAULT '[]'::jsonb,
    UNIQUE (discovery_run_id, column_id)
);

CREATE TABLE IF NOT EXISTS column_classifications (
    classification_id BIGSERIAL PRIMARY KEY,
    discovery_run_id UUID NOT NULL REFERENCES discovery_runs(discovery_run_id),
    column_id BIGINT NOT NULL REFERENCES discovered_columns(column_id),
    display_classification VARCHAR(32) NOT NULL,
    sensitive_data_type VARCHAR(128),
    sensitivity_level VARCHAR(32),
    is_sensitive BOOLEAN NOT NULL,
    confidence NUMERIC(5,4) NOT NULL CHECK (confidence BETWEEN 0 AND 1),
    reason TEXT NOT NULL,
    inference_basis JSONB NOT NULL DEFAULT '[]'::jsonb,
    needs_human_review BOOLEAN NOT NULL DEFAULT FALSE,
    review_reason TEXT,
    classifier_type VARCHAR(32) NOT NULL DEFAULT 'GPT_4O',
    classifier_version VARCHAR(64) NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (discovery_run_id, column_id)
);

CREATE TABLE IF NOT EXISTS dependency_edges (
    edge_id BIGSERIAL PRIMARY KEY,
    discovery_run_id UUID NOT NULL REFERENCES discovery_runs(discovery_run_id),
    source_object_id BIGINT REFERENCES discovered_objects(object_id),
    target_object_id BIGINT REFERENCES discovered_objects(object_id),
    relationship_type VARCHAR(64) NOT NULL,
    source_column VARCHAR(255),
    target_column VARCHAR(255),
    evidence_source VARCHAR(64) NOT NULL,
    confidence NUMERIC(5,4) CHECK (confidence BETWEEN 0 AND 1),
    details JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE TABLE IF NOT EXISTS hipaa_findings (
    finding_id BIGSERIAL PRIMARY KEY,
    discovery_run_id UUID NOT NULL REFERENCES discovery_runs(discovery_run_id),
    classification_id BIGINT NOT NULL REFERENCES column_classifications(classification_id),
    severity VARCHAR(32) NOT NULL,
    finding TEXT NOT NULL,
    recommendation TEXT NOT NULL,
    confidence NUMERIC(5,4) NOT NULL CHECK (confidence BETWEEN 0 AND 1),
    needs_human_review BOOLEAN NOT NULL DEFAULT FALSE,
    review_reason TEXT,
    verification_status VARCHAR(32) NOT NULL DEFAULT 'PROVISIONAL',
    agent_version VARCHAR(64) NOT NULL,
    UNIQUE (discovery_run_id, classification_id)
);

CREATE TABLE IF NOT EXISTS hipaa_scores (
    score_id BIGSERIAL PRIMARY KEY,
    discovery_run_id UUID NOT NULL UNIQUE REFERENCES discovery_runs(discovery_run_id),
    score NUMERIC(5,2) NOT NULL CHECK (score BETWEEN 0 AND 100),
    risk_band VARCHAR(32) NOT NULL,
    phi_columns_checked INTEGER NOT NULL,
    severity_counts JSONB NOT NULL,
    policy_version VARCHAR(64) NOT NULL,
    calculated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS audit_events (
    audit_event_id BIGSERIAL PRIMARY KEY,
    actor_id VARCHAR(255),
    action VARCHAR(128) NOT NULL,
    connection_id BIGINT,
    discovery_run_id UUID,
    outcome VARCHAR(32) NOT NULL,
    safe_details JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
