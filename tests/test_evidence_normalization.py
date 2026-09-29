from src.tools.evidence_normalization import (
    normalize_mysql_access_evidence,
)


def test_normalizes_global_mysql_permission():
    raw = [{
        "evidence_type": "DATABASE_PERMISSIONS",
        "source": "MYSQL_USER_PRIVILEGES",
        "scope": "GLOBAL",
        "database_name": "premier",
        "collection_status": "COLLECTED",
        "records": [{
            "principal": "'nupstream'@'%'",
            "privilege_type": "SELECT",
            "is_grantable": "NO",
        }],
        "record_count": 1,
    }]
    item = normalize_mysql_access_evidence(
        raw,
        tenant_id=1,
        connection_id=7,
        discovery_run_id="run-123",
    )[0]
    assert item.principal.principal_name == "nupstream"
    assert item.principal.principal_host == "%"
    assert item.resource.resource_type == "GLOBAL"
    assert item.observation["privilege"] == "SELECT"
    assert item.observation["inherited"] is True


def test_normalizes_table_mysql_permission():
    raw = [{
        "evidence_type": "DATABASE_PERMISSIONS",
        "source": "MYSQL_TABLE_PRIVILEGES",
        "scope": "TABLE",
        "database_name": "premier",
        "collection_status": "COLLECTED",
        "records": [{
            "principal": "'claims_user'@'localhost'",
            "schema_name": "premier",
            "table_name": "claims",
            "privilege_type": "SELECT",
            "is_grantable": "NO",
        }],
        "record_count": 1,
    }]
    item = normalize_mysql_access_evidence(
        raw,
        tenant_id=1,
        connection_id=7,
        discovery_run_id="run-123",
    )[0]
    assert item.resource.qualified_name == "premier.claims"
    assert item.resource.resource_type == "TABLE"
    assert item.observation["inherited"] is False


def test_empty_collection_is_persisted_as_collection_observation():
    raw = [{
        "evidence_type": "DATABASE_PERMISSIONS",
        "source": "MYSQL_COLUMN_PRIVILEGES",
        "scope": "COLUMN",
        "database_name": "premier",
        "collection_status": "COLLECTED",
        "records": [],
        "record_count": 0,
    }]
    item = normalize_mysql_access_evidence(
        raw,
        tenant_id=1,
        connection_id=7,
        discovery_run_id="run-123",
    )[0]
    assert item.evidence_type == "DATABASE_PERMISSION_COLLECTION"
    assert item.observation["record_count"] == 0
    assert item.raw_reference["source_view"] == "MYSQL_COLUMN_PRIVILEGES"
