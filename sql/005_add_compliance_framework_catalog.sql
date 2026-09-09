BEGIN;

CREATE TABLE IF NOT EXISTS demooc28.compliance_frameworks (
    framework_id BIGSERIAL PRIMARY KEY,
    framework_code VARCHAR(64) NOT NULL,
    framework_name VARCHAR(255) NOT NULL,
    description TEXT,
    region VARCHAR(255),
    implementation_status VARCHAR(32) NOT NULL DEFAULT 'PLANNED',
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_compliance_framework_code UNIQUE (framework_code),
    CONSTRAINT ck_compliance_framework_code
        CHECK (btrim(framework_code) <> ''),
    CONSTRAINT ck_compliance_framework_name
        CHECK (btrim(framework_name) <> ''),
    CONSTRAINT ck_compliance_framework_status
        CHECK (implementation_status IN ('AVAILABLE', 'PLANNED', 'DISABLED'))
);

CREATE TABLE IF NOT EXISTS demooc28.policy_pack_versions (
    policy_pack_version_id BIGSERIAL PRIMARY KEY,
    framework_id BIGINT NOT NULL
        REFERENCES demooc28.compliance_frameworks(framework_id)
        ON DELETE CASCADE,
    version VARCHAR(64) NOT NULL,
    status VARCHAR(32) NOT NULL DEFAULT 'DRAFT',
    scoring_enabled BOOLEAN NOT NULL DEFAULT TRUE,
    effective_from DATE,
    effective_to DATE,
    policy_metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_policy_pack_framework_version
        UNIQUE (framework_id, version),
    CONSTRAINT ck_policy_pack_version
        CHECK (btrim(version) <> ''),
    CONSTRAINT ck_policy_pack_status
        CHECK (status IN ('DRAFT', 'ACTIVE', 'RETIRED')),
    CONSTRAINT ck_policy_pack_effective_dates
        CHECK (
            effective_to IS NULL
            OR effective_from IS NULL
            OR effective_to >= effective_from
        )
);

INSERT INTO demooc28.compliance_frameworks (
    framework_code,
    framework_name,
    description,
    region,
    implementation_status,
    is_active
)
VALUES
    ('HIPAA', 'HIPAA',
     'Health information compliance assessment policy pack.',
     'United States', 'AVAILABLE', TRUE),
    ('GDPR', 'General Data Protection Regulation',
     'Personal data compliance assessment policy pack.',
     'European Union', 'PLANNED', TRUE),
    ('DPDP', 'Digital Personal Data Protection Act',
     'Digital personal data compliance assessment policy pack.',
     'India', 'PLANNED', TRUE),
    ('CCPA_CPRA', 'CCPA / CPRA',
     'California privacy compliance assessment policy pack.',
     'California, United States', 'PLANNED', TRUE),
    ('PCI_DSS', 'PCI DSS',
     'Payment-card data security assessment policy pack.',
     'Global', 'PLANNED', TRUE),
    ('GLBA', 'GLBA',
     'Financial information safeguards assessment policy pack.',
     'United States', 'PLANNED', TRUE),
    ('PIPEDA', 'PIPEDA',
     'Personal information protection assessment policy pack.',
     'Canada', 'PLANNED', TRUE)
ON CONFLICT (framework_code) DO UPDATE SET
    framework_name = EXCLUDED.framework_name,
    description = EXCLUDED.description,
    region = EXCLUDED.region,
    implementation_status = EXCLUDED.implementation_status,
    is_active = EXCLUDED.is_active;

INSERT INTO demooc28.policy_pack_versions (
    framework_id,
    version,
    status,
    scoring_enabled,
    effective_from,
    policy_metadata
)
SELECT
    framework_id,
    '1.0',
    CASE
        WHEN framework_code = 'HIPAA' THEN 'ACTIVE'
        ELSE 'DRAFT'
    END,
    TRUE,
    CASE
        WHEN framework_code = 'HIPAA' THEN CURRENT_DATE
        ELSE NULL
    END,
    jsonb_build_object(
        'framework_code', framework_code,
        'source', 'PRODUCT_MANAGED',
        'review_required', TRUE
    )
FROM demooc28.compliance_frameworks
ON CONFLICT (framework_id, version) DO UPDATE SET
    status = EXCLUDED.status,
    scoring_enabled = EXCLUDED.scoring_enabled,
    effective_from = EXCLUDED.effective_from,
    policy_metadata = EXCLUDED.policy_metadata;

DROP TRIGGER IF EXISTS
    trg_compliance_frameworks_updated_at
    ON demooc28.compliance_frameworks;
CREATE TRIGGER trg_compliance_frameworks_updated_at
BEFORE UPDATE ON demooc28.compliance_frameworks
FOR EACH ROW EXECUTE FUNCTION demooc28.set_updated_at();

DROP TRIGGER IF EXISTS
    trg_policy_pack_versions_updated_at
    ON demooc28.policy_pack_versions;
CREATE TRIGGER trg_policy_pack_versions_updated_at
BEFORE UPDATE ON demooc28.policy_pack_versions
FOR EACH ROW EXECUTE FUNCTION demooc28.set_updated_at();

CREATE INDEX IF NOT EXISTS idx_compliance_frameworks_active
    ON demooc28.compliance_frameworks(is_active, implementation_status);

CREATE INDEX IF NOT EXISTS idx_policy_pack_versions_framework
    ON demooc28.policy_pack_versions(framework_id, status);

COMMIT;
