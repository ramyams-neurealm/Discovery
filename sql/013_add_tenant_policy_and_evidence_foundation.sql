BEGIN;

-- ============================================================
-- Phase 2A: multi-tenant policy and normalized evidence foundation
-- Keeps existing compliance tables and extends the architecture.
-- ============================================================

-- 1. Tenants
CREATE TABLE IF NOT EXISTS demooc28.tenants (
    tenant_id BIGSERIAL PRIMARY KEY,
    tenant_code VARCHAR(128) NOT NULL,
    tenant_name VARCHAR(255) NOT NULL,
    status VARCHAR(32) NOT NULL DEFAULT 'ACTIVE',
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_tenant_code UNIQUE (tenant_code),
    CONSTRAINT ck_tenant_code_not_blank CHECK (btrim(tenant_code) <> ''),
    CONSTRAINT ck_tenant_name_not_blank CHECK (btrim(tenant_name) <> ''),
    CONSTRAINT ck_tenant_status CHECK (
        status IN ('ACTIVE', 'INACTIVE', 'SUSPENDED')
    )
);

-- Create a safe tenant for existing single-tenant records.
INSERT INTO demooc28.tenants (
    tenant_code,
    tenant_name,
    status
)
VALUES (
    'DEFAULT',
    'Default Tenant',
    'ACTIVE'
)
ON CONFLICT (tenant_code) DO NOTHING;

-- Add tenant ownership to existing datasource connections.
ALTER TABLE demooc28.datasource_connections
    ADD COLUMN IF NOT EXISTS tenant_id BIGINT;

UPDATE demooc28.datasource_connections
SET tenant_id = (
    SELECT tenant_id
    FROM demooc28.tenants
    WHERE tenant_code = 'DEFAULT'
)
WHERE tenant_id IS NULL;

ALTER TABLE demooc28.datasource_connections
    ALTER COLUMN tenant_id SET NOT NULL;

ALTER TABLE demooc28.datasource_connections
    DROP CONSTRAINT IF EXISTS fk_datasource_connections_tenant;

ALTER TABLE demooc28.datasource_connections
    ADD CONSTRAINT fk_datasource_connections_tenant
    FOREIGN KEY (tenant_id)
    REFERENCES demooc28.tenants(tenant_id);

-- Connection names are unique inside a tenant, not globally.
ALTER TABLE demooc28.datasource_connections
    DROP CONSTRAINT IF EXISTS uq_datasource_connection_name;

CREATE UNIQUE INDEX IF NOT EXISTS uq_datasource_connection_tenant_name
    ON demooc28.datasource_connections(tenant_id, connection_name);

-- 2. Client-defined logical principal groups
CREATE TABLE IF NOT EXISTS demooc28.tenant_principal_groups (
    principal_group_id BIGSERIAL PRIMARY KEY,
    tenant_id BIGINT NOT NULL
        REFERENCES demooc28.tenants(tenant_id) ON DELETE CASCADE,
    group_code VARCHAR(128) NOT NULL,
    group_name VARCHAR(255) NOT NULL,
    description TEXT,
    status VARCHAR(32) NOT NULL DEFAULT 'ACTIVE',
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_tenant_principal_group_code
        UNIQUE (tenant_id, group_code),
    CONSTRAINT ck_principal_group_code_not_blank
        CHECK (btrim(group_code) <> ''),
    CONSTRAINT ck_principal_group_name_not_blank
        CHECK (btrim(group_name) <> ''),
    CONSTRAINT ck_principal_group_status
        CHECK (status IN ('ACTIVE', 'INACTIVE'))
);

CREATE TABLE IF NOT EXISTS demooc28.tenant_principal_group_members (
    principal_group_member_id BIGSERIAL PRIMARY KEY,
    principal_group_id BIGINT NOT NULL
        REFERENCES demooc28.tenant_principal_groups(principal_group_id)
        ON DELETE CASCADE,
    connection_id BIGINT
        REFERENCES demooc28.datasource_connections(connection_id)
        ON DELETE CASCADE,
    principal_type VARCHAR(64) NOT NULL,
    principal_name VARCHAR(512) NOT NULL,
    principal_source VARCHAR(64) NOT NULL DEFAULT 'DATABASE',
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_principal_group_member UNIQUE (
        principal_group_id,
        connection_id,
        principal_type,
        principal_name,
        principal_source
    ),
    CONSTRAINT ck_principal_type CHECK (
        principal_type IN (
            'DATABASE_USER',
            'DATABASE_ROLE',
            'IDENTITY_USER',
            'IDENTITY_GROUP',
            'SERVICE_ACCOUNT',
            'SERVICE_PRINCIPAL',
            'PUBLIC'
        )
    ),
    CONSTRAINT ck_principal_source CHECK (
        principal_source IN (
            'DATABASE',
            'MICROSOFT_ENTRA_ID',
            'OKTA',
            'LDAP',
            'ACTIVE_DIRECTORY',
            'CLIENT_DEFINED'
        )
    ),
    CONSTRAINT ck_principal_name_not_blank
        CHECK (btrim(principal_name) <> '')
);

-- 3. Tenant-configurable client policies
CREATE TABLE IF NOT EXISTS demooc28.client_policies (
    client_policy_id BIGSERIAL PRIMARY KEY,
    tenant_id BIGINT NOT NULL
        REFERENCES demooc28.tenants(tenant_id) ON DELETE CASCADE,
    policy_code VARCHAR(128) NOT NULL,
    policy_name VARCHAR(255) NOT NULL,
    policy_type VARCHAR(64) NOT NULL,

    classification VARCHAR(64),
    sensitive_data_type VARCHAR(128),

    scope_type VARCHAR(32) NOT NULL,
    connection_id BIGINT
        REFERENCES demooc28.datasource_connections(connection_id)
        ON DELETE CASCADE,
    catalog_name VARCHAR(255),
    schema_name VARCHAR(255),
    table_name VARCHAR(255),
    column_name VARCHAR(255),

    principal_selector_type VARCHAR(64) NOT NULL,
    principal_selector_value VARCHAR(512) NOT NULL,

    effect VARCHAR(32) NOT NULL,
    allowed_privileges JSONB NOT NULL DEFAULT '[]'::jsonb,
    conditions JSONB NOT NULL DEFAULT '{}'::jsonb,
    priority INTEGER NOT NULL DEFAULT 100,

    status VARCHAR(32) NOT NULL DEFAULT 'DRAFT',
    effective_from DATE,
    effective_to DATE,
    approved_by VARCHAR(255),
    approved_at TIMESTAMPTZ,
    review_due_at TIMESTAMPTZ,

    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT uq_client_policy_code UNIQUE (tenant_id, policy_code),
    CONSTRAINT ck_client_policy_code_not_blank
        CHECK (btrim(policy_code) <> ''),
    CONSTRAINT ck_client_policy_name_not_blank
        CHECK (btrim(policy_name) <> ''),
    CONSTRAINT ck_client_policy_type CHECK (
        policy_type IN (
            'DATA_ACCESS',
            'DATA_MASKING',
            'DATA_RETENTION',
            'AUDIT_REQUIREMENT',
            'TRANSMISSION_SECURITY',
            'STORAGE_PROTECTION'
        )
    ),
    CONSTRAINT ck_client_policy_scope_type CHECK (
        scope_type IN (
            'TENANT',
            'CONNECTION',
            'CLASSIFICATION',
            'SCHEMA',
            'TABLE',
            'COLUMN'
        )
    ),
    CONSTRAINT ck_client_policy_principal_selector CHECK (
        principal_selector_type IN (
            'EXACT_PRINCIPAL',
            'DATABASE_ROLE',
            'CLIENT_PRINCIPAL_GROUP',
            'IDENTITY_GROUP',
            'SERVICE_ACCOUNT',
            'ALL_PRINCIPALS'
        )
    ),
    CONSTRAINT ck_client_policy_effect CHECK (
        effect IN ('ALLOW', 'DENY', 'ALLOW_WITH_CONDITIONS')
    ),
    CONSTRAINT ck_client_policy_status CHECK (
        status IN ('DRAFT', 'ACTIVE', 'INACTIVE', 'RETIRED')
    ),
    CONSTRAINT ck_client_policy_priority CHECK (
        priority BETWEEN 0 AND 1000
    ),
    CONSTRAINT ck_client_policy_privileges_array CHECK (
        jsonb_typeof(allowed_privileges) = 'array'
    ),
    CONSTRAINT ck_client_policy_conditions_object CHECK (
        jsonb_typeof(conditions) = 'object'
    ),
    CONSTRAINT ck_client_policy_effective_dates CHECK (
        effective_to IS NULL
        OR effective_from IS NULL
        OR effective_to >= effective_from
    ),
    CONSTRAINT ck_client_policy_scope_fields CHECK (
        (scope_type = 'TENANT')
        OR (scope_type = 'CONNECTION' AND connection_id IS NOT NULL)
        OR (scope_type = 'CLASSIFICATION' AND classification IS NOT NULL)
        OR (
            scope_type = 'SCHEMA'
            AND connection_id IS NOT NULL
            AND schema_name IS NOT NULL
        )
        OR (
            scope_type = 'TABLE'
            AND connection_id IS NOT NULL
            AND schema_name IS NOT NULL
            AND table_name IS NOT NULL
        )
        OR (
            scope_type = 'COLUMN'
            AND connection_id IS NOT NULL
            AND schema_name IS NOT NULL
            AND table_name IS NOT NULL
            AND column_name IS NOT NULL
        )
    )
);

-- 4. Normalized raw evidence store
CREATE TABLE IF NOT EXISTS demooc28.collected_evidence (
    evidence_id BIGSERIAL PRIMARY KEY,
    tenant_id BIGINT NOT NULL
        REFERENCES demooc28.tenants(tenant_id) ON DELETE CASCADE,
    connection_id BIGINT
        REFERENCES demooc28.datasource_connections(connection_id)
        ON DELETE CASCADE,
    discovery_run_id UUID
        REFERENCES demooc28.discovery_runs(discovery_run_id)
        ON DELETE CASCADE,

    evidence_category VARCHAR(64) NOT NULL,
    evidence_type VARCHAR(64) NOT NULL,

    source_type VARCHAR(32) NOT NULL,
    source_system VARCHAR(64) NOT NULL,
    collector_name VARCHAR(128) NOT NULL,
    collector_version VARCHAR(64) NOT NULL,

    principal_data JSONB NOT NULL DEFAULT '{}'::jsonb,
    resource_data JSONB NOT NULL DEFAULT '{}'::jsonb,
    observation_data JSONB NOT NULL DEFAULT '{}'::jsonb,

    collection_status VARCHAR(32) NOT NULL,
    collected_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    valid_until TIMESTAMPTZ,
    raw_reference JSONB NOT NULL DEFAULT '{}'::jsonb,
    error_data JSONB,
    evidence_hash VARCHAR(64),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT ck_collected_evidence_category_not_blank
        CHECK (btrim(evidence_category) <> ''),
    CONSTRAINT ck_collected_evidence_type_not_blank
        CHECK (btrim(evidence_type) <> ''),
    CONSTRAINT ck_collected_evidence_source_type CHECK (
        source_type IN (
            'DATABASE',
            'CLOUD',
            'IDENTITY_PROVIDER',
            'MANUAL',
            'APPLICATION'
        )
    ),
    CONSTRAINT ck_collected_evidence_status CHECK (
        collection_status IN (
            'COLLECTED',
            'PARTIALLY_COLLECTED',
            'PERMISSION_DENIED',
            'NOT_SUPPORTED',
            'NOT_CONFIGURED',
            'COLLECTION_FAILED'
        )
    ),
    CONSTRAINT ck_collected_evidence_principal_object CHECK (
        jsonb_typeof(principal_data) = 'object'
    ),
    CONSTRAINT ck_collected_evidence_resource_object CHECK (
        jsonb_typeof(resource_data) = 'object'
    ),
    CONSTRAINT ck_collected_evidence_observation_object CHECK (
        jsonb_typeof(observation_data) = 'object'
    ),
    CONSTRAINT ck_collected_evidence_raw_reference_object CHECK (
        jsonb_typeof(raw_reference) = 'object'
    ),
    CONSTRAINT ck_collected_evidence_error_object CHECK (
        error_data IS NULL OR jsonb_typeof(error_data) = 'object'
    ),
    CONSTRAINT ck_collected_evidence_validity CHECK (
        valid_until IS NULL OR valid_until >= collected_at
    )
);

-- 5. Many-to-many links from control results to raw evidence and policies
CREATE TABLE IF NOT EXISTS demooc28.control_evidence_links (
    control_evidence_link_id BIGSERIAL PRIMARY KEY,
    control_result_id BIGINT NOT NULL
        REFERENCES demooc28.compliance_control_results(control_result_id)
        ON DELETE CASCADE,
    evidence_id BIGINT NOT NULL
        REFERENCES demooc28.collected_evidence(evidence_id)
        ON DELETE CASCADE,
    usage_type VARCHAR(32) NOT NULL DEFAULT 'SUPPORTING',
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_control_evidence_link
        UNIQUE (control_result_id, evidence_id),
    CONSTRAINT ck_control_evidence_usage_type CHECK (
        usage_type IN ('PRIMARY', 'SUPPORTING', 'CONFLICTING')
    )
);

CREATE TABLE IF NOT EXISTS demooc28.control_policy_links (
    control_policy_link_id BIGSERIAL PRIMARY KEY,
    control_result_id BIGINT NOT NULL
        REFERENCES demooc28.compliance_control_results(control_result_id)
        ON DELETE CASCADE,
    client_policy_id BIGINT NOT NULL
        REFERENCES demooc28.client_policies(client_policy_id)
        ON DELETE CASCADE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_control_policy_link
        UNIQUE (control_result_id, client_policy_id)
);

-- 6. Indexes
CREATE INDEX IF NOT EXISTS idx_datasource_connections_tenant
    ON demooc28.datasource_connections(tenant_id, is_active);

CREATE INDEX IF NOT EXISTS idx_principal_groups_tenant
    ON demooc28.tenant_principal_groups(tenant_id, status);

CREATE INDEX IF NOT EXISTS idx_principal_group_members_lookup
    ON demooc28.tenant_principal_group_members(
        principal_group_id,
        connection_id,
        principal_type,
        principal_name
    );

CREATE INDEX IF NOT EXISTS idx_client_policies_resolution
    ON demooc28.client_policies(
        tenant_id,
        status,
        scope_type,
        connection_id,
        classification,
        schema_name,
        table_name,
        column_name,
        priority DESC
    );

CREATE INDEX IF NOT EXISTS idx_client_policies_allowed_privileges
    ON demooc28.client_policies USING GIN (allowed_privileges);

CREATE INDEX IF NOT EXISTS idx_client_policies_conditions
    ON demooc28.client_policies USING GIN (conditions);

CREATE INDEX IF NOT EXISTS idx_collected_evidence_run_category
    ON demooc28.collected_evidence(
        discovery_run_id,
        evidence_category,
        collection_status
    );

CREATE INDEX IF NOT EXISTS idx_collected_evidence_tenant_source
    ON demooc28.collected_evidence(
        tenant_id,
        source_type,
        source_system,
        collected_at DESC
    );

CREATE INDEX IF NOT EXISTS idx_collected_evidence_principal
    ON demooc28.collected_evidence USING GIN (principal_data);

CREATE INDEX IF NOT EXISTS idx_collected_evidence_resource
    ON demooc28.collected_evidence USING GIN (resource_data);

CREATE INDEX IF NOT EXISTS idx_collected_evidence_observation
    ON demooc28.collected_evidence USING GIN (observation_data);

-- 7. Updated-at triggers
DROP TRIGGER IF EXISTS trg_tenants_updated_at
    ON demooc28.tenants;
CREATE TRIGGER trg_tenants_updated_at
BEFORE UPDATE ON demooc28.tenants
FOR EACH ROW EXECUTE FUNCTION demooc28.set_updated_at();

DROP TRIGGER IF EXISTS trg_tenant_principal_groups_updated_at
    ON demooc28.tenant_principal_groups;
CREATE TRIGGER trg_tenant_principal_groups_updated_at
BEFORE UPDATE ON demooc28.tenant_principal_groups
FOR EACH ROW EXECUTE FUNCTION demooc28.set_updated_at();

DROP TRIGGER IF EXISTS trg_tenant_principal_group_members_updated_at
    ON demooc28.tenant_principal_group_members;
CREATE TRIGGER trg_tenant_principal_group_members_updated_at
BEFORE UPDATE ON demooc28.tenant_principal_group_members
FOR EACH ROW EXECUTE FUNCTION demooc28.set_updated_at();

DROP TRIGGER IF EXISTS trg_client_policies_updated_at
    ON demooc28.client_policies;
CREATE TRIGGER trg_client_policies_updated_at
BEFORE UPDATE ON demooc28.client_policies
FOR EACH ROW EXECUTE FUNCTION demooc28.set_updated_at();

COMMIT;
