BEGIN;

-- Phase 1:
-- Allow triggers to be stored as discovered database objects.

ALTER TABLE demooc28.discovered_objects
    DROP CONSTRAINT IF EXISTS
        ck_discovered_object_type;

ALTER TABLE demooc28.discovered_objects
    ADD CONSTRAINT ck_discovered_object_type
    CHECK (
        object_type IN (
            'TABLE',
            'VIEW',
            'MATERIALIZED_VIEW',
            'PROCEDURE',
            'FUNCTION',
            'TRIGGER'
        )
    );


-- Phase 2:
-- Allow normalized read, write, call, and foreign-key relationships.

ALTER TABLE demooc28.dependency_edges
    DROP CONSTRAINT IF EXISTS
        ck_dependency_relationship_type;

ALTER TABLE demooc28.dependency_edges
    ADD CONSTRAINT ck_dependency_relationship_type
    CHECK (
        relationship_type IN (
            'FOREIGN_KEY',
            'READS',
            'WRITES',
            'CALLS',

            -- Retained for backward compatibility with existing rows.
            'VIEW_READS_TABLE',
            'PROCEDURE_READS_TABLE',
            'PROCEDURE_WRITES_TABLE',
            'FUNCTION_READS_TABLE'
        )
    );


-- Phase 2:
-- Allow trigger definitions as dependency evidence.

ALTER TABLE demooc28.dependency_edges
    DROP CONSTRAINT IF EXISTS
        ck_dependency_evidence_source;

ALTER TABLE demooc28.dependency_edges
    ADD CONSTRAINT ck_dependency_evidence_source
    CHECK (
        evidence_source IN (
            'SOURCE_CATALOG',
            'DDL',
            'VIEW_DEFINITION',
            'PROCEDURE_DEFINITION',
            'FUNCTION_DEFINITION',
            'TRIGGER_DEFINITION',
            'GPT_ASSISTED_RESOLUTION'
        )
    );

COMMIT;