BEGIN;

-- ============================================================
-- Extensions and schema
-- ============================================================

BEGIN;

-- ============================================================
-- Extensions and schema
-- ============================================================

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

    -- Future secret-manager reference.
    credential_reference VARCHAR(512),

    -- DEVELOPMENT PROTOTYPE ONLY.
    -- Never return this value through APIs or write it to logs.
    password_plaintext TEXT,

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
    error_code VARCHAR(64),
    error_message TEXT,
    started_by VARCHAR(255),
    started_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_discovery_runs_connection
        FOREIGN KEY (connection_id)
        REFERENCES demooc28.datasource_connections(connection_id)
        ON DELETE RESTRICT,
    CONSTRAINT ck_discovery_requested_scopes_array
        CHECK (jsonb_typeof(requested_scopes) = 'array'),
    CONSTRAINT ck_discovery_effective_scopes_array
        CHECK (jsonb_typeof(effective_scopes) = 'array'),
    CONSTRAINT ck_discovery_run_status
        CHECK (status IN (
            'PENDING',
            'RUNNING',
            'SUCCEEDED',
            'PARTIALLY_COMPLETED',
            'FAILED',
            'CANCELLED'
        )),
    CONSTRAINT ck_discovery_current_stage
        CHECK (
            current_stage IS NULL OR current_stage IN (
                'CONNECTION_VALIDATION',
                'METADATA_PROFILING',
                'COLUMN_CLASSIFICATION',
                'DEPENDENCY_MAPPING',
                'HIPAA_COMPLIANCE',
                'REPORT_FINALIZATION'
            )
        ),
    CONSTRAINT ck_discovery_progress
        CHECK (progress_percentage BETWEEN 0 AND 100),
    CONSTRAINT ck_discovery_completion_time
        CHECK (completed_at IS NULL OR completed_at >= started_at)
);

-- ============================================================
-- 3. Individual stage progress used by the progress UI
-- ============================================================

CREATE TABLE IF NOT EXISTS demooc28.discovery_run_stages (
    stage_id BIGSERIAL PRIMARY KEY,
    discovery_run_id UUID NOT NULL,
    stage_name VARCHAR(64) NOT NULL,
    stage_status VARCHAR(32) NOT NULL DEFAULT 'PENDING',
    processed_items INTEGER NOT NULL DEFAULT 0,
    total_items INTEGER NOT NULL DEFAULT 0,
    attempt_number INTEGER NOT NULL DEFAULT 1,
    message TEXT,
    error_code VARCHAR(64),
    error_message TEXT,
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_discovery_stage_run
        FOREIGN KEY (discovery_run_id)
        REFERENCES demooc28.discovery_runs(discovery_run_id)
        ON DELETE CASCADE,
    CONSTRAINT ck_discovery_stage_name
        CHECK (stage_name IN (
            'CONNECTION_VALIDATION',
            'METADATA_PROFILING',
            'COLUMN_CLASSIFICATION',
            'DEPENDENCY_MAPPING',
            'HIPAA_COMPLIANCE',
            'REPORT_FINALIZATION'
        )),
    CONSTRAINT ck_discovery_stage_status
        CHECK (stage_status IN (
            'PENDING',
            'RUNNING',
            'COMPLETED',
            'COMPLETED_WITH_WARNINGS',
            'SKIPPED',
            'FAILED',
            'CANCELLED'
        )),
    CONSTRAINT ck_discovery_stage_counts
        CHECK (
            processed_items >= 0
            AND total_items >= 0
            AND processed_items <= total_items
        ),
    CONSTRAINT ck_discovery_stage_attempt
        CHECK (attempt_number >= 1),
    CONSTRAINT ck_discovery_stage_completion_time
        CHECK (
            completed_at IS NULL
            OR started_at IS NULL
            OR completed_at >= started_at
        ),
    CONSTRAINT uq_discovery_run_stage
        UNIQUE (discovery_run_id, stage_name)
);

-- ============================================================
-- 4. Objects discovered during one run
-- ============================================================

CREATE TABLE IF NOT EXISTS demooc28.discovered_objects (
    object_id BIGSERIAL PRIMARY KEY,
    discovery_run_id UUID NOT NULL,
    connection_id BIGINT NOT NULL,
    schema_name VARCHAR(255) NOT NULL,
    object_name VARCHAR(255) NOT NULL,
    object_type VARCHAR(64) NOT NULL,
    object_ddl TEXT,
    object_metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_discovered_object_run
        FOREIGN KEY (discovery_run_id)
        REFERENCES demooc28.discovery_runs(discovery_run_id)
        ON DELETE CASCADE,
    CONSTRAINT fk_discovered_object_connection
        FOREIGN KEY (connection_id)
        REFERENCES demooc28.datasource_connections(connection_id)
        ON DELETE RESTRICT,
    CONSTRAINT ck_discovered_schema_name_not_blank
        CHECK (btrim(schema_name) <> ''),
    CONSTRAINT ck_discovered_object_name_not_blank
        CHECK (btrim(object_name) <> ''),
    CONSTRAINT ck_discovered_object_type
        CHECK (object_type IN (
            'TABLE',
            'VIEW',
            'MATERIALIZED_VIEW',
            'PROCEDURE',
            'FUNCTION'
        )),
    CONSTRAINT ck_discovered_object_metadata_object
        CHECK (jsonb_typeof(object_metadata) = 'object'),
    CONSTRAINT uq_discovered_object
        UNIQUE (
            discovery_run_id,
            schema_name,
            object_name,
            object_type
        )
);

-- ============================================================
-- 5. Columns discovered for tables and views
-- ============================================================

CREATE TABLE IF NOT EXISTS demooc28.discovered_columns (
    column_id BIGSERIAL PRIMARY KEY,
    discovery_run_id UUID NOT NULL,
    object_id BIGINT NOT NULL,
    column_name VARCHAR(255) NOT NULL,
    ordinal_position INTEGER,
    data_type VARCHAR(255) NOT NULL,
    nullable BOOLEAN,
    default_value TEXT,
    is_primary_key BOOLEAN NOT NULL DEFAULT FALSE,
    is_foreign_key BOOLEAN NOT NULL DEFAULT FALSE,
    column_metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_discovered_column_run
        FOREIGN KEY (discovery_run_id)
        REFERENCES demooc28.discovery_runs(discovery_run_id)
        ON DELETE CASCADE,
    CONSTRAINT fk_discovered_column_object
        FOREIGN KEY (object_id)
        REFERENCES demooc28.discovered_objects(object_id)
        ON DELETE CASCADE,
    CONSTRAINT ck_discovered_column_name_not_blank
        CHECK (btrim(column_name) <> ''),
    CONSTRAINT ck_discovered_column_type_not_blank
        CHECK (btrim(data_type) <> ''),
    CONSTRAINT ck_discovered_column_ordinal
        CHECK (ordinal_position IS NULL OR ordinal_position >= 1),
    CONSTRAINT ck_discovered_column_metadata_object
        CHECK (jsonb_typeof(column_metadata) = 'object'),
    CONSTRAINT uq_discovered_column
        UNIQUE (discovery_run_id, object_id, column_name)
);

-- ============================================================
-- 6. Table-level profiles produced during mandatory profiling
-- ============================================================

CREATE TABLE IF NOT EXISTS demooc28.table_profiles (
    table_profile_id BIGSERIAL PRIMARY KEY,
    discovery_run_id UUID NOT NULL,
    object_id BIGINT NOT NULL,
    row_count BIGINT,
    column_count INTEGER NOT NULL,
    average_null_percentage NUMERIC(7,4),
    profiling_method VARCHAR(32) NOT NULL DEFAULT 'EXACT',
    profile_metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_table_profile_run
        FOREIGN KEY (discovery_run_id)
        REFERENCES demooc28.discovery_runs(discovery_run_id)
        ON DELETE CASCADE,
    CONSTRAINT fk_table_profile_object
        FOREIGN KEY (object_id)
        REFERENCES demooc28.discovered_objects(object_id)
        ON DELETE CASCADE,
    CONSTRAINT ck_table_profile_row_count
        CHECK (row_count IS NULL OR row_count >= 0),
    CONSTRAINT ck_table_profile_column_count
        CHECK (column_count >= 0),
    CONSTRAINT ck_table_profile_average_null
        CHECK (
            average_null_percentage IS NULL
            OR average_null_percentage BETWEEN 0 AND 100
        ),
    CONSTRAINT ck_table_profile_method
        CHECK (profiling_method IN ('EXACT', 'APPROXIMATE', 'SAMPLED')),
    CONSTRAINT ck_table_profile_metadata_object
        CHECK (jsonb_typeof(profile_metadata) = 'object'),
    CONSTRAINT uq_table_profile
        UNIQUE (discovery_run_id, object_id)
);

-- ============================================================
-- 7. Column-level profiles
-- Only masked samples may be persisted here.
-- ============================================================

CREATE TABLE IF NOT EXISTS demooc28.column_profiles (
    column_profile_id BIGSERIAL PRIMARY KEY,
    discovery_run_id UUID NOT NULL,
    column_id BIGINT NOT NULL,
    null_percentage NUMERIC(7,4),
    distinct_count BIGINT,
    distinct_count_is_approximate BOOLEAN NOT NULL DEFAULT FALSE,
    masked_samples JSONB NOT NULL DEFAULT '[]'::jsonb,
    profile_metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_column_profile_run
        FOREIGN KEY (discovery_run_id)
        REFERENCES demooc28.discovery_runs(discovery_run_id)
        ON DELETE CASCADE,
    CONSTRAINT fk_column_profile_column
        FOREIGN KEY (column_id)
        REFERENCES demooc28.discovered_columns(column_id)
        ON DELETE CASCADE,
    CONSTRAINT ck_column_profile_null_percentage
        CHECK (
            null_percentage IS NULL
            OR null_percentage BETWEEN 0 AND 100
        ),
    CONSTRAINT ck_column_profile_distinct_count
        CHECK (distinct_count IS NULL OR distinct_count >= 0),
    CONSTRAINT ck_column_profile_samples_array
        CHECK (jsonb_typeof(masked_samples) = 'array'),
    CONSTRAINT ck_column_profile_sample_limit
        CHECK (jsonb_array_length(masked_samples) <= 3),
    CONSTRAINT ck_column_profile_metadata_object
        CHECK (jsonb_typeof(profile_metadata) = 'object'),
    CONSTRAINT uq_column_profile
        UNIQUE (discovery_run_id, column_id)
);

-- ============================================================
-- 8. GPT-assisted column classification output
-- ============================================================

CREATE TABLE IF NOT EXISTS demooc28.column_classifications (
    classification_id BIGSERIAL PRIMARY KEY,
    discovery_run_id UUID NOT NULL,
    column_id BIGINT NOT NULL,
    display_classification VARCHAR(32) NOT NULL,
    sensitive_data_type VARCHAR(128),
    sensitivity_level VARCHAR(32),
    is_sensitive BOOLEAN NOT NULL,
    confidence NUMERIC(5,4) NOT NULL,
    reason TEXT NOT NULL,
    inference_basis JSONB NOT NULL DEFAULT '[]'::jsonb,
    needs_human_review BOOLEAN NOT NULL DEFAULT FALSE,
    review_reason TEXT,
    classifier_type VARCHAR(32) NOT NULL DEFAULT 'GPT_4O',
    classifier_version VARCHAR(64) NOT NULL,
    evidence_mode VARCHAR(32) NOT NULL DEFAULT 'METADATA_PROFILE',
    verification_status VARCHAR(32) NOT NULL DEFAULT 'PROVISIONAL',
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_column_classification_run
        FOREIGN KEY (discovery_run_id)
        REFERENCES demooc28.discovery_runs(discovery_run_id)
        ON DELETE CASCADE,
    CONSTRAINT fk_column_classification_column
        FOREIGN KEY (column_id)
        REFERENCES demooc28.discovered_columns(column_id)
        ON DELETE CASCADE,
    CONSTRAINT ck_column_display_classification
        CHECK (display_classification IN (
            'PUBLIC',
            'PII',
            'PHI',
            'FINANCIAL',
            'SENSITIVE'
        )),
    CONSTRAINT ck_column_sensitivity_level
        CHECK (
            sensitivity_level IS NULL OR sensitivity_level IN (
                'PUBLIC',
                'INTERNAL',
                'CONFIDENTIAL',
                'RESTRICTED'
            )
        ),
    CONSTRAINT ck_column_classification_confidence
        CHECK (confidence BETWEEN 0 AND 1),
    CONSTRAINT ck_column_classification_reason_not_blank
        CHECK (btrim(reason) <> ''),
    CONSTRAINT ck_column_inference_basis_array
        CHECK (jsonb_typeof(inference_basis) = 'array'),
    CONSTRAINT ck_column_review_reason
        CHECK (
            needs_human_review = FALSE
            OR review_reason IS NOT NULL
        ),
    CONSTRAINT ck_column_classifier_type
        CHECK (classifier_type IN ('GPT_4O', 'RULE_BASED', 'HUMAN_OVERRIDE')),
    CONSTRAINT ck_column_evidence_mode
        CHECK (evidence_mode IN ('DDL_ONLY', 'METADATA_PROFILE', 'SAMPLED_PROFILE')),
    CONSTRAINT ck_column_verification_status
        CHECK (verification_status IN ('PROVISIONAL', 'REVIEWED', 'CONFIRMED', 'REJECTED')),
    CONSTRAINT uq_column_classification
        UNIQUE (discovery_run_id, column_id)
);

-- ============================================================
-- 9. Dependency graph edges
-- ============================================================

CREATE TABLE IF NOT EXISTS demooc28.dependency_edges (
    edge_id BIGSERIAL PRIMARY KEY,
    discovery_run_id UUID NOT NULL,
    source_object_id BIGINT NOT NULL,
    target_object_id BIGINT NOT NULL,
    relationship_type VARCHAR(64) NOT NULL,
    source_column VARCHAR(255),
    target_column VARCHAR(255),
    evidence_source VARCHAR(64) NOT NULL,
    confidence NUMERIC(5,4),
    verification_status VARCHAR(32) NOT NULL DEFAULT 'PROVISIONAL',
    details JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_dependency_edge_run
        FOREIGN KEY (discovery_run_id)
        REFERENCES demooc28.discovery_runs(discovery_run_id)
        ON DELETE CASCADE,
    CONSTRAINT fk_dependency_edge_source
        FOREIGN KEY (source_object_id)
        REFERENCES demooc28.discovered_objects(object_id)
        ON DELETE CASCADE,
    CONSTRAINT fk_dependency_edge_target
        FOREIGN KEY (target_object_id)
        REFERENCES demooc28.discovered_objects(object_id)
        ON DELETE CASCADE,
    CONSTRAINT ck_dependency_distinct_objects
        CHECK (source_object_id <> target_object_id),
    CONSTRAINT ck_dependency_relationship_type
        CHECK (relationship_type IN (
            'FOREIGN_KEY',
            'VIEW_READS_TABLE',
            'PROCEDURE_READS_TABLE',
            'PROCEDURE_WRITES_TABLE',
            'FUNCTION_READS_TABLE'
        )),
    CONSTRAINT ck_dependency_evidence_source
        CHECK (evidence_source IN (
            'SOURCE_CATALOG',
            'DDL',
            'VIEW_DEFINITION',
            'PROCEDURE_DEFINITION',
            'FUNCTION_DEFINITION',
            'GPT_ASSISTED_RESOLUTION'
        )),
    CONSTRAINT ck_dependency_confidence
        CHECK (confidence IS NULL OR confidence BETWEEN 0 AND 1),
    CONSTRAINT ck_dependency_verification_status
        CHECK (verification_status IN ('PROVISIONAL', 'VERIFIED', 'REJECTED')),
    CONSTRAINT ck_dependency_details_object
        CHECK (jsonb_typeof(details) = 'object')
);

-- Prevent duplicate edges while treating NULL columns consistently.
CREATE UNIQUE INDEX IF NOT EXISTS uq_dependency_edge
    ON demooc28.dependency_edges (
        discovery_run_id,
        source_object_id,
        target_object_id,
        relationship_type,
        COALESCE(source_column, ''),
        COALESCE(target_column, '')
    );

-- ============================================================
-- 10. HIPAA findings, one per PHI classification per run
-- ============================================================

CREATE TABLE IF NOT EXISTS demooc28.hipaa_findings (
    finding_id BIGSERIAL PRIMARY KEY,
    discovery_run_id UUID NOT NULL,
    classification_id BIGINT NOT NULL,
    severity VARCHAR(32) NOT NULL,
    finding TEXT NOT NULL,
    recommendation TEXT NOT NULL,
    confidence NUMERIC(5,4) NOT NULL,
    needs_human_review BOOLEAN NOT NULL DEFAULT FALSE,
    review_reason TEXT,
    verification_status VARCHAR(32) NOT NULL DEFAULT 'PROVISIONAL',
    agent_version VARCHAR(64) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_hipaa_finding_run
        FOREIGN KEY (discovery_run_id)
        REFERENCES demooc28.discovery_runs(discovery_run_id)
        ON DELETE CASCADE,
    CONSTRAINT fk_hipaa_finding_classification
        FOREIGN KEY (classification_id)
        REFERENCES demooc28.column_classifications(classification_id)
        ON DELETE CASCADE,
    CONSTRAINT ck_hipaa_finding_severity
        CHECK (severity IN ('GOOD', 'NEEDS_REVIEW', 'SERIOUS', 'CRITICAL')),
    CONSTRAINT ck_hipaa_finding_not_blank
        CHECK (btrim(finding) <> ''),
    CONSTRAINT ck_hipaa_recommendation_not_blank
        CHECK (btrim(recommendation) <> ''),
    CONSTRAINT ck_hipaa_finding_confidence
        CHECK (confidence BETWEEN 0 AND 1),
    CONSTRAINT ck_hipaa_finding_review_reason
        CHECK (
            needs_human_review = FALSE
            OR review_reason IS NOT NULL
        ),
    CONSTRAINT ck_hipaa_finding_verification
        CHECK (verification_status IN ('PROVISIONAL', 'REVIEWED', 'CONFIRMED', 'REJECTED')),
    CONSTRAINT uq_hipaa_finding
        UNIQUE (discovery_run_id, classification_id)
);

-- ============================================================
-- 11. Deterministically calculated HIPAA score
-- ============================================================

CREATE TABLE IF NOT EXISTS demooc28.hipaa_scores (
    score_id BIGSERIAL PRIMARY KEY,
    discovery_run_id UUID NOT NULL,
    score NUMERIC(5,2) NOT NULL,
    risk_band VARCHAR(32) NOT NULL,
    phi_columns_checked INTEGER NOT NULL,
    severity_counts JSONB NOT NULL,
    policy_version VARCHAR(64) NOT NULL,
    calculated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_hipaa_score_run
        FOREIGN KEY (discovery_run_id)
        REFERENCES demooc28.discovery_runs(discovery_run_id)
        ON DELETE CASCADE,
    CONSTRAINT ck_hipaa_score
        CHECK (score BETWEEN 0 AND 100),
    CONSTRAINT ck_hipaa_risk_band
        CHECK (risk_band IN (
            'NOT_APPLICABLE',
            'GOOD',
            'NEEDS_REVIEW',
            'SERIOUS',
            'CRITICAL'
        )),
    CONSTRAINT ck_hipaa_phi_columns_checked
        CHECK (phi_columns_checked >= 0),
    CONSTRAINT ck_hipaa_severity_counts_object
        CHECK (jsonb_typeof(severity_counts) = 'object'),
    CONSTRAINT uq_hipaa_score_run
        UNIQUE (discovery_run_id)
);

-- ============================================================
-- 12. Immutable-safe audit events
-- Application permissions should allow INSERT and SELECT but
-- should not allow UPDATE or DELETE for normal application roles.
-- ============================================================

CREATE TABLE IF NOT EXISTS demooc28.audit_events (
    audit_event_id BIGSERIAL PRIMARY KEY,
    actor_id VARCHAR(255),
    action VARCHAR(128) NOT NULL,
    connection_id BIGINT,
    discovery_run_id UUID,
    outcome VARCHAR(32) NOT NULL,
    safe_details JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_audit_event_connection
        FOREIGN KEY (connection_id)
        REFERENCES demooc28.datasource_connections(connection_id)
        ON DELETE SET NULL,
    CONSTRAINT fk_audit_event_run
        FOREIGN KEY (discovery_run_id)
        REFERENCES demooc28.discovery_runs(discovery_run_id)
        ON DELETE SET NULL,
    CONSTRAINT ck_audit_action_not_blank
        CHECK (btrim(action) <> ''),
    CONSTRAINT ck_audit_outcome
        CHECK (outcome IN ('SUCCESS', 'FAILURE', 'DENIED', 'WARNING')),
    CONSTRAINT ck_audit_safe_details_object
        CHECK (jsonb_typeof(safe_details) = 'object')
);

-- ============================================================
-- Indexes for API and agent queries
-- ============================================================

CREATE INDEX IF NOT EXISTS idx_connections_active
    ON demooc28.datasource_connections (is_active);

CREATE INDEX IF NOT EXISTS idx_connections_discovery_status
    ON demooc28.datasource_connections (discovery_status);

CREATE INDEX IF NOT EXISTS idx_discovery_runs_connection_started
    ON demooc28.discovery_runs (connection_id, started_at DESC);

CREATE INDEX IF NOT EXISTS idx_discovery_runs_status
    ON demooc28.discovery_runs (status);

CREATE INDEX IF NOT EXISTS idx_discovery_run_stages_run
    ON demooc28.discovery_run_stages (discovery_run_id);

CREATE INDEX IF NOT EXISTS idx_discovered_objects_run
    ON demooc28.discovered_objects (discovery_run_id);

CREATE INDEX IF NOT EXISTS idx_discovered_objects_lookup
    ON demooc28.discovered_objects (
        discovery_run_id,
        schema_name,
        object_name
    );

CREATE INDEX IF NOT EXISTS idx_discovered_columns_run
    ON demooc28.discovered_columns (discovery_run_id);

CREATE INDEX IF NOT EXISTS idx_discovered_columns_object
    ON demooc28.discovered_columns (object_id, ordinal_position);

CREATE INDEX IF NOT EXISTS idx_table_profiles_run
    ON demooc28.table_profiles (discovery_run_id);

CREATE INDEX IF NOT EXISTS idx_column_profiles_run
    ON demooc28.column_profiles (discovery_run_id);

CREATE INDEX IF NOT EXISTS idx_classifications_run_category
    ON demooc28.column_classifications (
        discovery_run_id,
        display_classification
    );

CREATE INDEX IF NOT EXISTS idx_classifications_review
    ON demooc28.column_classifications (
        discovery_run_id,
        needs_human_review
    );

CREATE INDEX IF NOT EXISTS idx_dependency_edges_run
    ON demooc28.dependency_edges (discovery_run_id);

CREATE INDEX IF NOT EXISTS idx_dependency_edges_source
    ON demooc28.dependency_edges (discovery_run_id, source_object_id);

CREATE INDEX IF NOT EXISTS idx_dependency_edges_target
    ON demooc28.dependency_edges (discovery_run_id, target_object_id);

CREATE INDEX IF NOT EXISTS idx_hipaa_findings_run_severity
    ON demooc28.hipaa_findings (discovery_run_id, severity);

CREATE INDEX IF NOT EXISTS idx_hipaa_findings_review
    ON demooc28.hipaa_findings (
        discovery_run_id,
        needs_human_review
    );

CREATE INDEX IF NOT EXISTS idx_audit_events_connection_created
    ON demooc28.audit_events (connection_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_audit_events_run_created
    ON demooc28.audit_events (discovery_run_id, created_at DESC);

-- ============================================================
-- updated_at triggers
-- ============================================================

DROP TRIGGER IF EXISTS trg_datasource_connections_updated_at
    ON demooc28.datasource_connections;
CREATE TRIGGER trg_datasource_connections_updated_at
BEFORE UPDATE ON demooc28.datasource_connections
FOR EACH ROW EXECUTE FUNCTION demooc28.set_updated_at();

DROP TRIGGER IF EXISTS trg_discovery_runs_updated_at
    ON demooc28.discovery_runs;
CREATE TRIGGER trg_discovery_runs_updated_at
BEFORE UPDATE ON demooc28.discovery_runs
FOR EACH ROW EXECUTE FUNCTION demooc28.set_updated_at();

DROP TRIGGER IF EXISTS trg_discovery_run_stages_updated_at
    ON demooc28.discovery_run_stages;
CREATE TRIGGER trg_discovery_run_stages_updated_at
BEFORE UPDATE ON demooc28.discovery_run_stages
FOR EACH ROW EXECUTE FUNCTION demooc28.set_updated_at();

DROP TRIGGER IF EXISTS trg_discovered_objects_updated_at
    ON demooc28.discovered_objects;
CREATE TRIGGER trg_discovered_objects_updated_at
BEFORE UPDATE ON demooc28.discovered_objects
FOR EACH ROW EXECUTE FUNCTION demooc28.set_updated_at();

DROP TRIGGER IF EXISTS trg_discovered_columns_updated_at
    ON demooc28.discovered_columns;
CREATE TRIGGER trg_discovered_columns_updated_at
BEFORE UPDATE ON demooc28.discovered_columns
FOR EACH ROW EXECUTE FUNCTION demooc28.set_updated_at();

DROP TRIGGER IF EXISTS trg_table_profiles_updated_at
    ON demooc28.table_profiles;
CREATE TRIGGER trg_table_profiles_updated_at
BEFORE UPDATE ON demooc28.table_profiles
FOR EACH ROW EXECUTE FUNCTION demooc28.set_updated_at();

DROP TRIGGER IF EXISTS trg_column_profiles_updated_at
    ON demooc28.column_profiles;
CREATE TRIGGER trg_column_profiles_updated_at
BEFORE UPDATE ON demooc28.column_profiles
FOR EACH ROW EXECUTE FUNCTION demooc28.set_updated_at();

DROP TRIGGER IF EXISTS trg_column_classifications_updated_at
    ON demooc28.column_classifications;
CREATE TRIGGER trg_column_classifications_updated_at
BEFORE UPDATE ON demooc28.column_classifications
FOR EACH ROW EXECUTE FUNCTION demooc28.set_updated_at();

DROP TRIGGER IF EXISTS trg_dependency_edges_updated_at
    ON demooc28.dependency_edges;
CREATE TRIGGER trg_dependency_edges_updated_at
BEFORE UPDATE ON demooc28.dependency_edges
FOR EACH ROW EXECUTE FUNCTION demooc28.set_updated_at();

DROP TRIGGER IF EXISTS trg_hipaa_findings_updated_at
    ON demooc28.hipaa_findings;
CREATE TRIGGER trg_hipaa_findings_updated_at
BEFORE UPDATE ON demooc28.hipaa_findings
FOR EACH ROW EXECUTE FUNCTION demooc28.set_updated_at();

DROP TRIGGER IF EXISTS trg_hipaa_scores_updated_at
    ON demooc28.hipaa_scores;
CREATE TRIGGER trg_hipaa_scores_updated_at
BEFORE UPDATE ON demooc28.hipaa_scores
FOR EACH ROW EXECUTE FUNCTION demooc28.set_updated_at();

COMMIT;
