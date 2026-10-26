from contextlib import contextmanager
import threading
from types import SimpleNamespace
from unittest.mock import Mock

from src.agents import metadata_profiling_agent as metadata_module
from src.agents.metadata_profiling_agent import (
    MetadataDiscoveryProfilingAgent,
)
from src.tools import profiling_tools


class PostgreSQLConnector:
    def __init__(self):
        self.connection = Mock()


def test_zero_row_table_is_completed_and_keeps_column_profiles(monkeypatch):
    agent = MetadataDiscoveryProfilingAgent.__new__(
        MetadataDiscoveryProfilingAgent
    )
    agent.settings = SimpleNamespace(metadata_stage_timeout_seconds=30)
    agent.repository = Mock()
    objects = [
        {
            "object_id": 1,
            "schema_name": "public",
            "object_name": "empty_table",
            "object_type": "TABLE",
            "columns": [
                {
                    "column_id": 2,
                    "column_name": "record_id",
                }
            ],
        }
    ]
    table_profiles = [{"object_id": 1, "row_count": 0}]
    column_profiles = [{"object_id": 1, "column_id": 2}]

    monkeypatch.setattr(
        metadata_module,
        "discover_database_metadata",
        lambda **kwargs: objects,
    )
    agent.repository.save_discovered_metadata.return_value = objects
    monkeypatch.setattr(
        metadata_module,
        "profile_tables",
        lambda **kwargs: (table_profiles, column_profiles),
    )
    agent.repository.save_profiles.return_value = (
        table_profiles,
        column_profiles,
    )

    result = agent.run(
        run_id="run-123",
        connection_id=7,
        source_connection=PostgreSQLConnector(),
        selected_objects=[
            {"object_name": "empty_table", "object_type": "TABLE"}
        ],
    )

    assert result["objects"] == objects
    assert result["column_profiles"] == column_profiles
    stage_updates = [
        call.kwargs
        for call in agent.repository.update_stage.call_args_list
    ]
    assert any(update.get("stage_status") == "COMPLETED" for update in stage_updates)
    assert not any(
        update.get("stage_status") == "COMPLETED_WITH_WARNINGS"
        for update in stage_updates
    )
    assert any(
        "1 table(s) had zero rows" in update.get("message", "")
        for update in stage_updates
    )


def test_profile_tables_accepts_lowercase_table_type(monkeypatch):
    connector = type("PostgreSQLConnector", (), {})()
    connector.connection = Mock()
    table = {
        "object_id": 1,
        "schema_name": "public",
        "object_name": "example",
        "object_type": "table",
        "columns": [],
    }
    monkeypatch.setattr(profiling_tools, "_scalar", lambda *args: 3)
    monkeypatch.setattr(profiling_tools, "_vendor", lambda *args: "POSTGRESQL")

    table_profiles, column_profiles = profiling_tools.profile_tables(
        source_connector=connector,
        objects=[table],
    )

    assert len(table_profiles) == 1
    assert table_profiles[0]["row_count"] == 3
    assert column_profiles == []


def test_column_sampling_failure_does_not_discard_other_profiles(monkeypatch):
    connector = type("PostgreSQLConnector", (), {})()
    connector.connection = Mock()
    columns = [
        {"column_name": "good_column"},
        {"column_name": "bad_column", "data_type": "unsupported"},
    ]
    table = {
        "object_id": 1,
        "schema_name": "public",
        "object_name": "example",
        "object_type": "TABLE",
        "columns": columns,
    }
    errors = []
    monkeypatch.setattr(profiling_tools, "_scalar", lambda *args: 3)

    def profile_column(**kwargs):
        if kwargs["column"]["column_name"] == "bad_column":
            raise ValueError("unsupported column type")
        return {
            "column_id": 10,
            "object_id": 1,
            "column_name": "good_column",
            "null_percentage": 0.0,
        }

    monkeypatch.setattr(profiling_tools, "_profile_column", profile_column)
    monkeypatch.setattr(profiling_tools, "_vendor", lambda *args: "POSTGRESQL")

    table_profiles, column_profiles = profiling_tools.profile_tables(
        source_connector=connector,
        objects=[table],
        errors=errors,
    )

    assert len(table_profiles) == 1
    assert [item["column_name"] for item in column_profiles] == ["good_column"]
    assert len(errors) == 1
    assert "bad_column" in errors[0]


def test_postgresql_jsonb_uses_text_for_distinct_queries():
    connector = type("PostgreSQLConnector", (), {})()
    expression = profiling_tools._distinct_expression(
        source_connector=connector,
        column={"native_data_type": "jsonb"},
        column_ref='"payload"',
    )

    assert expression == 'CAST("payload" AS TEXT)'


def test_postgresql_sampling_query_failure_rolls_back_to_savepoint():
    class TransactionConnection:
        def __init__(self):
            self.rollback_count = 0
            self.cursor_calls = 0

        @contextmanager
        def transaction(self):
            try:
                yield
            except Exception:
                self.rollback_count += 1
                raise

        def cursor(self):
            self.cursor_calls += 1
            call_number = self.cursor_calls

            class Cursor:
                def execute(self, query):
                    if call_number == 1:
                        raise TimeoutError("query timeout")

                def fetchone(self):
                    return (7,)

                def close(self):
                    pass

            return Cursor()

    connector = type("PostgreSQLConnector", (), {})()
    connector.connection = TransactionConnection()

    try:
        profiling_tools._scalar(connector, "SELECT 1")
    except TimeoutError:
        pass
    else:
        raise AssertionError("The first sampling query should fail")

    assert profiling_tools._scalar(connector, "SELECT 7") == 7
    assert connector.connection.rollback_count == 1


def test_jsonb_column_uses_truncated_text_sample_without_distinct_count(monkeypatch):
    connector = type("PostgreSQLConnector", (), {})()
    connector.connection = Mock()
    monkeypatch.setattr(profiling_tools, "_scalar", Mock(return_value=0))
    sample_mock = Mock(return_value=([], False))
    monkeypatch.setattr(profiling_tools, "_sample_values", sample_mock)
    monkeypatch.setattr(profiling_tools, "_vendor", lambda *_: "POSTGRESQL")

    profile = profiling_tools._profile_column(
        source_connector=connector,
        schema_name="public",
        table_name="events",
        row_count=1,
        column={
            "object_id": 2,
            "column_id": 3,
            "column_name": "payload",
            "data_type": "JSONB",
            "native_data_type": "jsonb",
        },
        all_columns=[],
    )

    assert profile["distinct_count"] is None
    assert sample_mock.call_args.kwargs["is_json_column"] is True
    assert "SUBSTRING(" in sample_mock.call_args.kwargs["sample_expression"]
    assert profile["sampling_warning"] is False


def test_sample_timeout_returns_empty_values_with_warning():
    class QueryCanceled(Exception):
        pass

    class TransactionConnection:
        @contextmanager
        def transaction(self):
            try:
                yield
            except Exception:
                raise

        def cursor(self):
            class Cursor:
                statements = []

                def execute(self, query):
                    self.statements.append(query)
                    if query.startswith("SELECT"):
                        raise QueryCanceled("statement timeout")

                def close(self):
                    pass

            return Cursor()

    connector = type("PostgreSQLConnector", (), {})()
    connector.connection = TransactionConnection()
    values, warning = profiling_tools._sample_values(
        source_connector=connector,
        table_ref='"public"."events"',
        column_ref='"payload"',
        sample_expression='SUBSTRING("payload"::text FROM 1 FOR 100)',
        is_json_column=True,
    )

    assert values == []
    assert warning is True


def test_multiple_tables_profile_concurrently_on_worker_connectors(monkeypatch):
    class PostgreSQLConnector:
        def __init__(self, config, password):
            self.config = config
            self.password = password
            self.connection = Mock()

        def connect(self):
            return self.connection

        def make_read_only(self):
            pass

        def close(self):
            pass

    source_connector = PostgreSQLConnector({}, "secret")
    barrier = threading.Barrier(2)
    observed_connector_ids = set()

    def profile_one_table(connector, database_object):
        observed_connector_ids.add(id(connector))
        barrier.wait(timeout=5)
        profile = {
            "object_id": database_object["object_id"],
            "table_name": database_object["object_name"],
        }
        return profile, [], []

    monkeypatch.setattr(
        profiling_tools,
        "_profile_one_table",
        profile_one_table,
    )
    objects = [
        {
            "object_id": 1,
            "schema_name": "public",
            "object_name": "first_table",
            "object_type": "TABLE",
        },
        {
            "object_id": 2,
            "schema_name": "public",
            "object_name": "second_table",
            "object_type": "TABLE",
        },
    ]

    table_profiles, column_profiles = profiling_tools.profile_tables(
        source_connector,
        objects,
    )

    assert len(table_profiles) == 2
    assert column_profiles == []
    assert len(observed_connector_ids) == 2


def test_postgresql_sample_and_metric_queries_are_bounded():
    class RecordingConnection:
        def __init__(self):
            self.statements = []

        @contextmanager
        def transaction(self):
            yield

        def cursor(self):
            connection = self

            class Cursor:
                def execute(self, query):
                    connection.statements.append(query)

                def fetchall(self):
                    return [("sample",)]

                def fetchone(self):
                    return (1,)

                def close(self):
                    pass

            return Cursor()

    connector = type("PostgreSQLConnector", (), {})()
    connector.connection = RecordingConnection()

    profiling_tools._sample_values(
        connector,
        '"public"."events"',
        '"event_name"',
        '"event_name"',
    )
    profiling_tools._scalar(
        connector,
        'SELECT COUNT(DISTINCT sampled_column) FROM '
        '(SELECT "event_name" AS sampled_column '
        'FROM "public"."events" LIMIT 250) AS sampled_values',
    )

    statements = connector.connection.statements
    assert statements[0] == "SET LOCAL statement_timeout = '3000ms'"
    assert "LIMIT 250" in statements[1]
    assert statements[2] == "SET LOCAL statement_timeout = '3000ms'"
    assert "LIMIT 250" in statements[3]


def test_metadata_discovery_exception_is_returned_for_diagnostics(monkeypatch):
    agent = MetadataDiscoveryProfilingAgent.__new__(
        MetadataDiscoveryProfilingAgent
    )
    agent.settings = SimpleNamespace(metadata_stage_timeout_seconds=30)
    agent.repository = Mock()
    monkeypatch.setattr(
        metadata_module,
        "discover_database_metadata",
        Mock(side_effect=RuntimeError("catalog query timed out")),
    )

    result = agent.run(
        run_id="run-456",
        connection_id=7,
        source_connection=PostgreSQLConnector(),
        selected_objects=[],
    )

    assert result["metadata_error"] == "catalog query timed out"
    assert result["objects"] == []
    assert result["table_profiles"] == []
    assert result["column_profiles"] == []