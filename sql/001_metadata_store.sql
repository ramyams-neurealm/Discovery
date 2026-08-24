BEGIN;
CREATE EXTENSION IF NOT EXISTS pgcrypto;
CREATE SCHEMA IF NOT EXISTS demooc28;
CREATE OR REPLACE FUNCTION demooc28.set_updated_at() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN NEW.updated_at=CURRENT_TIMESTAMP; RETURN NEW; END $$;

CREATE TABLE IF NOT EXISTS demooc28.datasource_connections (
    connection_id BIGSERIAL PRIMARY KEY,

    connection_name VARCHAR(255) NOT NULL,

    database_type VARCHAR(32) NOT NULL,

    host VARCHAR(255) NOT NULL,

    port INTEGER NOT NULL,

    database_name VARCHAR(255) NOT NULL,

    username VARCHAR(255) NOT NULL,

    ssl_enabled BOOLEAN NOT NULL DEFAULT TRUE,

    credential_reference VARCHAR(512),

    password_encrypted BYTEA,

    is_active BOOLEAN NOT NULL DEFAULT TRUE,

    discovery_status VARCHAR(32)
        NOT NULL
        DEFAULT 'NOT_STARTED',

    last_discovered_at TIMESTAMPTZ,

    created_by VARCHAR(255),

    created_at TIMESTAMPTZ
        NOT NULL
        DEFAULT CURRENT_TIMESTAMP,

    updated_at TIMESTAMPTZ
        NOT NULL
        DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT uq_datasource_connection_name
        UNIQUE (connection_name),

    CONSTRAINT ck_datasource_database_type
        CHECK (
            database_type IN (
                'POSTGRESQL',
                'MYSQL',
                'SQL_SERVER',
                'ORACLE'
            )
        ),

    CONSTRAINT ck_datasource_port
        CHECK (
            port BETWEEN 1 AND 65535
        ),

    CONSTRAINT ck_datasource_connection_name
        CHECK (
            btrim(connection_name) <> ''
        ),

    CONSTRAINT ck_datasource_host
        CHECK (
            btrim(host) <> ''
        ),

    CONSTRAINT ck_datasource_database_name
        CHECK (
            btrim(database_name) <> ''
        ),

    CONSTRAINT ck_datasource_username
        CHECK (
            btrim(username) <> ''
        )
);
CREATE TABLE IF NOT EXISTS demooc28.discovery_runs (
 discovery_run_id UUID PRIMARY KEY DEFAULT gen_random_uuid(), connection_id BIGINT NOT NULL REFERENCES demooc28.datasource_connections(connection_id),
 requested_scopes JSONB NOT NULL DEFAULT '[]', effective_scopes JSONB NOT NULL DEFAULT '[]', status VARCHAR(32) NOT NULL DEFAULT 'PENDING',
 current_stage VARCHAR(64), progress_percentage NUMERIC(5,2) NOT NULL DEFAULT 0 CHECK(progress_percentage BETWEEN 0 AND 100),
 error_code VARCHAR(64), error_message TEXT, started_by VARCHAR(255), started_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
 completed_at TIMESTAMPTZ, created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP, updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS demooc28.discovery_run_stages (
 stage_id BIGSERIAL PRIMARY KEY, discovery_run_id UUID NOT NULL REFERENCES demooc28.discovery_runs(discovery_run_id) ON DELETE CASCADE,
 stage_name VARCHAR(64) NOT NULL, stage_status VARCHAR(32) NOT NULL DEFAULT 'PENDING', processed_items INTEGER NOT NULL DEFAULT 0,
 total_items INTEGER NOT NULL DEFAULT 0, attempt_number INTEGER NOT NULL DEFAULT 1, message TEXT, error_code VARCHAR(64), error_message TEXT,
 started_at TIMESTAMPTZ, completed_at TIMESTAMPTZ, created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
 updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP, UNIQUE(discovery_run_id,stage_name)
);
CREATE TABLE IF NOT EXISTS demooc28.discovered_objects (
 object_id BIGSERIAL PRIMARY KEY, discovery_run_id UUID NOT NULL REFERENCES demooc28.discovery_runs(discovery_run_id) ON DELETE CASCADE,
 connection_id BIGINT NOT NULL REFERENCES demooc28.datasource_connections(connection_id), schema_name VARCHAR(255) NOT NULL,
 object_name VARCHAR(255) NOT NULL, object_type VARCHAR(64) NOT NULL, object_ddl TEXT, object_metadata JSONB NOT NULL DEFAULT '{}',
 created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP, updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
 UNIQUE(discovery_run_id,schema_name,object_name,object_type)
);
CREATE TABLE IF NOT EXISTS demooc28.discovered_columns (
 column_id BIGSERIAL PRIMARY KEY, discovery_run_id UUID NOT NULL REFERENCES demooc28.discovery_runs(discovery_run_id) ON DELETE CASCADE,
 object_id BIGINT NOT NULL REFERENCES demooc28.discovered_objects(object_id) ON DELETE CASCADE, column_name VARCHAR(255) NOT NULL,
 ordinal_position INTEGER, data_type VARCHAR(255) NOT NULL, nullable BOOLEAN, default_value TEXT, is_primary_key BOOLEAN NOT NULL DEFAULT FALSE,
 is_foreign_key BOOLEAN NOT NULL DEFAULT FALSE, column_metadata JSONB NOT NULL DEFAULT '{}', created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
 updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP, UNIQUE(discovery_run_id,object_id,column_name)
);
CREATE TABLE IF NOT EXISTS demooc28.table_profiles (
 table_profile_id BIGSERIAL PRIMARY KEY, discovery_run_id UUID NOT NULL REFERENCES demooc28.discovery_runs(discovery_run_id) ON DELETE CASCADE,
 object_id BIGINT NOT NULL REFERENCES demooc28.discovered_objects(object_id) ON DELETE CASCADE, row_count BIGINT, column_count INTEGER NOT NULL,
 average_null_percentage NUMERIC(7,4), profiling_method VARCHAR(32) NOT NULL DEFAULT 'EXACT', profile_metadata JSONB NOT NULL DEFAULT '{}',
 created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP, updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP, UNIQUE(discovery_run_id,object_id)
);
CREATE TABLE IF NOT EXISTS demooc28.column_profiles (
 column_profile_id BIGSERIAL PRIMARY KEY, discovery_run_id UUID NOT NULL REFERENCES demooc28.discovery_runs(discovery_run_id) ON DELETE CASCADE,
 column_id BIGINT NOT NULL REFERENCES demooc28.discovered_columns(column_id) ON DELETE CASCADE, null_percentage NUMERIC(7,4), distinct_count BIGINT,
 distinct_count_is_approximate BOOLEAN NOT NULL DEFAULT FALSE, masked_samples JSONB NOT NULL DEFAULT '[]', profile_metadata JSONB NOT NULL DEFAULT '{}',
 created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP, updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP, UNIQUE(discovery_run_id,column_id)
);
CREATE TABLE IF NOT EXISTS demooc28.column_classifications (
 classification_id BIGSERIAL PRIMARY KEY, discovery_run_id UUID NOT NULL REFERENCES demooc28.discovery_runs(discovery_run_id) ON DELETE CASCADE,
 column_id BIGINT NOT NULL REFERENCES demooc28.discovered_columns(column_id) ON DELETE CASCADE, display_classification VARCHAR(32) NOT NULL,
 sensitive_data_type VARCHAR(128), sensitivity_level VARCHAR(32), is_sensitive BOOLEAN NOT NULL, confidence NUMERIC(5,4) NOT NULL,
 reason TEXT NOT NULL, inference_basis JSONB NOT NULL DEFAULT '[]', needs_human_review BOOLEAN NOT NULL DEFAULT FALSE, review_reason TEXT,
 classifier_type VARCHAR(32) NOT NULL DEFAULT 'GPT_4O', classifier_version VARCHAR(64) NOT NULL, evidence_mode VARCHAR(32) NOT NULL DEFAULT 'METADATA_PROFILE',
 verification_status VARCHAR(32) NOT NULL DEFAULT 'PROVISIONAL', created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
 updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP, UNIQUE(discovery_run_id,column_id)
);
CREATE TABLE IF NOT EXISTS demooc28.dependency_edges (
 edge_id BIGSERIAL PRIMARY KEY, discovery_run_id UUID NOT NULL REFERENCES demooc28.discovery_runs(discovery_run_id) ON DELETE CASCADE,
 source_object_id BIGINT NOT NULL REFERENCES demooc28.discovered_objects(object_id) ON DELETE CASCADE,
 target_object_id BIGINT NOT NULL REFERENCES demooc28.discovered_objects(object_id) ON DELETE CASCADE, relationship_type VARCHAR(64) NOT NULL,
 source_column VARCHAR(255), target_column VARCHAR(255), evidence_source VARCHAR(64) NOT NULL, confidence NUMERIC(5,4),
 verification_status VARCHAR(32) NOT NULL DEFAULT 'PROVISIONAL', details JSONB NOT NULL DEFAULT '{}', created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
 updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_dependency_edge ON demooc28.dependency_edges(discovery_run_id,source_object_id,target_object_id,relationship_type,COALESCE(source_column,''),COALESCE(target_column,''));
CREATE TABLE IF NOT EXISTS demooc28.hipaa_findings (
 finding_id BIGSERIAL PRIMARY KEY, discovery_run_id UUID NOT NULL REFERENCES demooc28.discovery_runs(discovery_run_id) ON DELETE CASCADE,
 classification_id BIGINT NOT NULL REFERENCES demooc28.column_classifications(classification_id) ON DELETE CASCADE, severity VARCHAR(32) NOT NULL,
 finding TEXT NOT NULL, recommendation TEXT NOT NULL, confidence NUMERIC(5,4) NOT NULL, needs_human_review BOOLEAN NOT NULL DEFAULT FALSE,
 review_reason TEXT, verification_status VARCHAR(32) NOT NULL DEFAULT 'PROVISIONAL', agent_version VARCHAR(64) NOT NULL,
 created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP, updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
 UNIQUE(discovery_run_id,classification_id)
);
CREATE TABLE IF NOT EXISTS demooc28.hipaa_scores (
 score_id BIGSERIAL PRIMARY KEY, discovery_run_id UUID NOT NULL UNIQUE REFERENCES demooc28.discovery_runs(discovery_run_id) ON DELETE CASCADE,
 score NUMERIC(5,2) NOT NULL, risk_band VARCHAR(32) NOT NULL, phi_columns_checked INTEGER NOT NULL, severity_counts JSONB NOT NULL,
 policy_version VARCHAR(64) NOT NULL, calculated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP, updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS demooc28.audit_events (
 audit_event_id BIGSERIAL PRIMARY KEY, actor_id VARCHAR(255), action VARCHAR(128) NOT NULL, connection_id BIGINT REFERENCES demooc28.datasource_connections(connection_id) ON DELETE SET NULL,
 discovery_run_id UUID REFERENCES demooc28.discovery_runs(discovery_run_id) ON DELETE SET NULL, outcome VARCHAR(32) NOT NULL,
 safe_details JSONB NOT NULL DEFAULT '{}', created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_runs_connection ON demooc28.discovery_runs(connection_id,started_at DESC);
CREATE INDEX IF NOT EXISTS idx_objects_run ON demooc28.discovered_objects(discovery_run_id);
CREATE INDEX IF NOT EXISTS idx_columns_run ON demooc28.discovered_columns(discovery_run_id);
CREATE INDEX IF NOT EXISTS idx_classifications_run ON demooc28.column_classifications(discovery_run_id,display_classification);
CREATE INDEX IF NOT EXISTS idx_dependencies_run ON demooc28.dependency_edges(discovery_run_id);
CREATE INDEX IF NOT EXISTS idx_hipaa_run ON demooc28.hipaa_findings(discovery_run_id,severity);

DO $$ DECLARE t text; BEGIN FOREACH t IN ARRAY ARRAY['datasource_connections','discovery_runs','discovery_run_stages','discovered_objects','discovered_columns','table_profiles','column_profiles','column_classifications','dependency_edges','hipaa_findings','hipaa_scores'] LOOP EXECUTE format('DROP TRIGGER IF EXISTS %I ON demooc28.%I','trg_'||t||'_updated_at',t); EXECUTE format('CREATE TRIGGER %I BEFORE UPDATE ON demooc28.%I FOR EACH ROW EXECUTE FUNCTION demooc28.set_updated_at()','trg_'||t||'_updated_at',t); END LOOP; END $$;
COMMIT;
