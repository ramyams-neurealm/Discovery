BEGIN;

-- 1. Add assignment, SLA due date, Compliance Lead sign-off, and activity history to compliance_findings
ALTER TABLE demooc28.compliance_findings
    ADD COLUMN IF NOT EXISTS assigned_to VARCHAR(128) NULL,
    ADD COLUMN IF NOT EXISTS due_date DATE NULL,
    ADD COLUMN IF NOT EXISTS approved_by VARCHAR(128) NULL,
    ADD COLUMN IF NOT EXISTS activity_log JSONB NOT NULL DEFAULT '[]'::jsonb;

-- 2. Create editable Organization Remediation Standards table
CREATE TABLE IF NOT EXISTS demooc28.remediation_standards (
    standard_id INT PRIMARY KEY DEFAULT 1 CHECK (standard_id = 1),
    critical_sla_days INT NOT NULL DEFAULT 3 CHECK (critical_sla_days >= 1),
    serious_sla_days INT NOT NULL DEFAULT 14 CHECK (serious_sla_days >= 1),
    needs_review_sla_days INT NOT NULL DEFAULT 30 CHECK (needs_review_sla_days >= 1),
    min_justification_chars INT NOT NULL DEFAULT 40 CHECK (min_justification_chars >= 0),
    require_lead_signoff BOOLEAN NOT NULL DEFAULT TRUE,
    preferred_fixes JSONB NOT NULL DEFAULT '{
        "PHI": "Tokenization (vault-backed, last 4 digits visible)",
        "PII": "AES-256 column-level encryption with RBAC",
        "SENSITIVE": "Cryptographic hashing (Argon2id / bcrypt) + access restriction",
        "FINANCIAL": "PCI-compliant vault tokenization",
        "DEFAULT": "Apply column-level encryption and role-based access control"
    }'::jsonb,
    updated_by VARCHAR(128) NULL,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Seed default organization standards row if not already present
INSERT INTO demooc28.remediation_standards (standard_id)
VALUES (1)
ON CONFLICT (standard_id) DO NOTHING;

COMMIT;