from __future__ import annotations

import re
import logging
import threading
from contextlib import nullcontext
from time import monotonic
from typing import Any
from concurrent.futures import ThreadPoolExecutor, as_completed, TimeoutError


MAX_SAMPLE_VALUES = 3
MAX_METRIC_ROWS = 250
_VALID_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_$#]*$")
_TABLE_OBJECT_TYPES = {"TABLE", "BASE TABLE", "PARTITIONED TABLE"}
MAX_PROFILE_WORKERS = 5
logger = logging.getLogger(__name__)


def is_table_object(database_object: dict[str, Any]) -> bool:
    object_type = str(database_object.get("object_type") or "")
    return object_type.strip().upper() in _TABLE_OBJECT_TYPES


def profile_tables(
    source_connector: Any,
    objects: list[dict[str, Any]],
    errors: list[str] | None = None,
):
    """Profile tables concurrently with an independent connector per worker and per-task timeouts."""
    table_profiles: list[dict[str, Any]] = []
    column_profiles: list[dict[str, Any]] = []
    profile_errors = errors if errors is not None else []
    table_objects = [item for item in objects if is_table_object(item)]

    # Enforce strict 15-second max timeout per table task
    TABLE_PROFILE_TIMEOUT = 15

    if len(table_objects) <= 1:
        results = []
        for item in table_objects:
            try:
                results.append(_profile_one_table(source_connector, item))
            except Exception as error:
                message = f"Profiling failed for {item.get('schema_name', '')}.{item.get('object_name', '')}: {error}"
                failed_cols = [
                    _failed_column_profile(
                        item.get("schema_name", ""),
                        item.get("object_name", ""),
                        col,
                        [message],
                    )
                    for col in item.get("columns", [])
                ]
                results.append((_failed_table_profile(item, message), failed_cols, [message]))
    else:
        thread_state = threading.local()
        connector_lock = threading.Lock()
        worker_connectors: list[Any] = []

        def profile_with_worker(database_object):
            connector = getattr(thread_state, "connector", None)
            if connector is None:
                try:
                    connector = _create_profile_worker_connector(source_connector)
                    thread_state.connector = connector
                    with connector_lock:
                        worker_connectors.append(connector)
                except Exception as error:
                    message = (
                        "Could not create independent profiling connection for "
                        f"{database_object.get('schema_name', '')}."
                        f"{database_object.get('object_name', '')}. "
                        f"Failure type: {error.__class__.__name__}. "
                        f"Driver message: {error}"
                    )
                    failed_columns = [
                        _failed_column_profile(
                            database_object.get("schema_name", ""),
                            database_object.get("object_name", ""),
                            column,
                            [message],
                        )
                        for column in database_object.get("columns", [])
                    ]
                    return (
                        _failed_table_profile(database_object, message),
                        failed_columns,
                        [message],
                    )
            
            try:
                return _profile_one_table(connector, database_object)
            except Exception as error:
                message = f"Table profiling execution error: {error}"
                failed_columns = [
                    _failed_column_profile(
                        database_object.get("schema_name", ""),
                        database_object.get("object_name", ""),
                        column,
                        [message],
                    )
                    for column in database_object.get("columns", [])
                ]
                return (_failed_table_profile(database_object, message), failed_columns, [message])

        results = []
        try:
            with ThreadPoolExecutor(
                max_workers=min(MAX_PROFILE_WORKERS, len(table_objects))
            ) as executor:
                # Submit tasks individually so timeouts can be enforced per task
                future_to_obj = {
                    executor.submit(profile_with_worker, obj): obj for obj in table_objects
                }
                for future in as_completed(future_to_obj):
                    database_object = future_to_obj[future]
                    try:
                        res = future.result(timeout=TABLE_PROFILE_TIMEOUT)
                        results.append(res)
                    except TimeoutError:
                        message = (
                            f"Profiling timed out after {TABLE_PROFILE_TIMEOUT}s for "
                            f"{database_object.get('schema_name', '')}.{database_object.get('object_name', '')}"
                        )
                        logger.warning(message)
                        failed_columns = [
                            _failed_column_profile(
                                database_object.get("schema_name", ""),
                                database_object.get("object_name", ""),
                                column,
                                [message],
                            )
                            for column in database_object.get("columns", [])
                        ]
                        results.append(
                            (_failed_table_profile(database_object, message), failed_columns, [message])
                        )
                    except Exception as error:
                        message = f"Unhandled exception during table profiling: {error}"
                        failed_columns = [
                            _failed_column_profile(
                                database_object.get("schema_name", ""),
                                database_object.get("object_name", ""),
                                column,
                                [message],
                            )
                            for column in database_object.get("columns", [])
                        ]
                        results.append(
                            (_failed_table_profile(database_object, message), failed_columns, [message])
                        )
        finally:
            for connector in worker_connectors:
                try:
                    connector.close()
                except Exception:
                    logger.warning(
                        "Could not close a table-profiling worker connection",
                        exc_info=True,
                    )

    for table_profile, column_profiles_for_table, table_errors in results:
        if table_profile is not None:
            table_profiles.append(table_profile)
        column_profiles.extend(column_profiles_for_table)
        profile_errors.extend(table_errors)

    return table_profiles, column_profiles


def _profile_one_table(
    source_connector: Any,
    database_object: dict[str, Any],
) -> tuple[dict[str, Any] | None, list[dict[str, Any]], list[str]]:
    """Profile one table and return local warnings without raising."""
    table_errors: list[str] = []
    schema_name = database_object["schema_name"]
    table_name = database_object["object_name"]
    columns = database_object.get("columns", [])

    try:
        row_count = _scalar(
            source_connector,
            _row_count_query(source_connector, schema_name, table_name),
        )
    except Exception as error:
        message = (
            f"Table row-count profiling failed for {schema_name}.{table_name}. "
            f"Failure type: {error.__class__.__name__}. Driver message: {error}"
        )
        table_errors.append(message)
        logger.warning("%s", message)
        failed_profiles = [
            _failed_column_profile(
                schema_name,
                table_name,
                column,
                [message],
            )
            for column in columns
        ]
        return _failed_table_profile(database_object, message), failed_profiles, table_errors

    current_profiles: list[dict[str, Any]] = []
    for column in columns:
        column_name = str(column.get("column_name", ""))
        print(
            f"[PROFILING] Profiling table: {table_name}, "
            f"column: {column_name}"
        )
        column_deadline = monotonic() + 5.0
        column_failed = False
        try:
            profile = _profile_column(
                source_connector=source_connector,
                schema_name=schema_name,
                table_name=table_name,
                row_count=row_count,
                column=column,
                all_columns=columns,
                timeout_deadline=column_deadline,
            )
        except Exception as error:
            message = (
                f"Column profiling failed for {schema_name}.{table_name}."
                f"{column.get('column_name')}. Data type: "
                f"{column.get('data_type')}. Native data type: "
                f"{column.get('native_data_type')}. Failure type: "
                f"{error.__class__.__name__}. Driver message: {error}"
            )
            logger.warning("%s", message)
            print(
                f"[PROFILING WARNING] Column {table_name}.{column_name} "
                "timed out or failed. Applying empty fallback profile."
            )
            table_errors.append(message)
            profile = _failed_column_profile(
                schema_name=schema_name,
                table_name=table_name,
                column=column,
                warnings=[message],
            )
            column_failed = True

        current_profiles.append(profile)
        if profile.get("sampling_warning") and not column_failed:
            warnings = profile["profile_metadata"].setdefault("warnings", [])
            if not warnings:
                warnings.append(
                    f"Sample query timed out for {schema_name}.{table_name}."
                    f"{column.get('column_name')}"
                )
            table_errors.extend(warnings)

    percentages = [
        profile["null_percentage"]
        for profile in current_profiles
        if profile.get("null_percentage") is not None
    ]
    average_null = (
        round(sum(percentages) / len(percentages), 4)
        if percentages
        else 0.0
    )
    vendor = _vendor(source_connector)
    table_profile = {
        "object_id": database_object["object_id"],
        "schema_name": schema_name,
        "table_name": table_name,
        "row_count": row_count,
        "column_count": len(columns),
        "average_null_percentage": average_null,
        "profiling_method": "SAMPLED" if vendor == "POSTGRESQL" else "EXACT",
        "profile_metadata": {
            "database_vendor": vendor,
            "row_count_is_sampled": vendor == "POSTGRESQL",
            "metric_sample_limit": MAX_METRIC_ROWS if vendor == "POSTGRESQL" else None,
        },
    }
    return table_profile, current_profiles, table_errors


def _create_profile_worker_connector(source_connector: Any) -> Any:
    connector = source_connector.__class__(
        source_connector.config,
        source_connector.password,
    )
    try:
        connector.connect()
        connector.make_read_only()
        _configure_profile_worker_timeout(connector)
    except Exception:
        connector.close()
        raise
    return connector


def _configure_profile_worker_timeout(source_connector: Any) -> None:
    connection = source_connector.connection
    vendor = _vendor(source_connector)
    if vendor == "POSTGRESQL":
        connection.execute("SET statement_timeout = '3000ms'")
    elif vendor == "MYSQL":
        cursor = connection.cursor()
        try:
            cursor.execute("SET SESSION max_execution_time = 3000")
        finally:
            cursor.close()
    elif vendor == "SQL_SERVER":
        connection.timeout = 3
    elif vendor == "ORACLE":
        connection.call_timeout = 3000


def _failed_table_profile(
    database_object: dict[str, Any],
    warning: str,
) -> dict[str, Any]:
    return {
        "object_id": database_object.get("object_id"),
        "schema_name": database_object.get("schema_name", ""),
        "table_name": database_object.get("object_name", ""),
        "row_count": None,
        "column_count": len(database_object.get("columns", [])),
        "average_null_percentage": None,
        "profiling_method": "FAILED",
        "profile_metadata": {"warnings": [warning]},
    }


def _profile_column(
    source_connector: Any,
    schema_name: str,
    table_name: str,
    row_count: int,
    column: dict[str, Any],
    all_columns: list[dict[str, Any]],
    timeout_deadline: float | None = None,
):
    column_name = column["column_name"]
    table_ref = _table_reference(
        source_connector,
        schema_name,
        table_name,
    )
    column_ref = _quote_identifier(source_connector, column_name)
    is_json_column = _is_postgresql_json_column(
        source_connector,
        column,
    )
    comparable_expression = _distinct_expression(
        source_connector=source_connector,
        column=column,
        column_ref=column_ref,
    )
    distinct_count_is_approximate = (
        _distinct_count_is_approximate(
            source_connector=source_connector,
            column=column,
        )
    )

    if _vendor(source_connector) == "POSTGRESQL":
        null_count_query = (
            f"SELECT COUNT(*) FROM (SELECT {column_ref} FROM {table_ref} "
            f"LIMIT {MAX_METRIC_ROWS}) AS sampled_column "
            f"WHERE {column_ref} IS NULL"
        )
    else:
        null_count_query = (
            f"SELECT COUNT(*) FROM {table_ref} "
            f"WHERE {column_ref} IS NULL"
        )
    null_count = _scalar(
        source_connector,
        null_count_query,
        timeout_deadline=timeout_deadline,
    )
    distinct_count = (
        None
        if is_json_column
        else _scalar(
            source_connector,
            (
                f"SELECT COUNT(DISTINCT sampled_column) FROM ("
                f"SELECT {comparable_expression} AS sampled_column "
                f"FROM {table_ref} WHERE {column_ref} IS NOT NULL "
                f"LIMIT {MAX_METRIC_ROWS}) AS sampled_values"
                if _vendor(source_connector) == "POSTGRESQL"
                else (
                    f"SELECT COUNT(DISTINCT {comparable_expression}) "
                    f"FROM {table_ref} WHERE {column_ref} IS NOT NULL"
                )
            ),
            timeout_deadline=timeout_deadline,
        )
    )
    sample_expression = (
        f"SUBSTRING({column_ref}::text FROM 1 FOR 100)"
        if is_json_column
        else comparable_expression
    )
    raw_samples, sampling_warning = _sample_values(
        source_connector=source_connector,
        table_ref=table_ref,
        column_ref=column_ref,
        sample_expression=sample_expression,
        is_json_column=is_json_column,
        timeout_deadline=timeout_deadline,
    )

    null_percentage = (
        0.0
        if row_count == 0
        else round((null_count / row_count) * 100, 4)
    )
    masked_samples = [mask_sample(value) for value in raw_samples]

    return {
        "column_id": column["column_id"],
        "object_id": column["object_id"],
        "schema_name": schema_name,
        "table_name": table_name,
        "column_name": column_name,
        "data_type": column["data_type"],
        "nullable": column.get("nullable"),
        "is_primary_key": column.get("is_primary_key", False),
        "is_foreign_key": column.get("is_foreign_key", False),
        "neighboring_columns": _neighboring_columns(column, all_columns),
        "null_percentage": null_percentage,
        "distinct_count": distinct_count,
        "distinct_count_is_approximate": (
            distinct_count_is_approximate
        ),
        "masked_samples": masked_samples,
        "sampling_warning": sampling_warning,
        "profile_metadata": {
            "null_count": null_count,
            "sample_count": len(masked_samples),
            "database_vendor": _vendor(source_connector),
            "sampling_status": "WARNING" if sampling_warning else "COMPLETED",
            "warnings": (
                ["Column value sampling failed or timed out"]
                if sampling_warning
                else []
            ),
        },
    }


def _failed_column_profile(
    schema_name: str,
    table_name: str,
    column: dict[str, Any],
    warnings: list[str],
) -> dict[str, Any]:
    """Return a persistable placeholder for one failed column sample."""
    return {
        "column_id": column.get("column_id"),
        "object_id": column.get("object_id"),
        "schema_name": schema_name,
        "table_name": table_name,
        "column_name": column.get("column_name", ""),
        "data_type": column.get("data_type", ""),
        "nullable": column.get("nullable"),
        "is_primary_key": column.get("is_primary_key", False),
        "is_foreign_key": column.get("is_foreign_key", False),
        "neighboring_columns": [],
        "null_percentage": None,
        "distinct_count": None,
        "distinct_count_is_approximate": False,
        "masked_samples": [],
        "sampling_warning": True,
        "profile_metadata": {
            "sample_count": 0,
            "sampling_status": "WARNING",
            "warnings": warnings,
        },
    }


def _row_count_query(
    source_connector: Any,
    schema_name: str,
    table_name: str,
):
    table_ref = _table_reference(
        source_connector,
        schema_name,
        table_name,
    )
    if _vendor(source_connector) == "POSTGRESQL":
        return (
            f"SELECT COUNT(*) FROM (SELECT 1 FROM {table_ref} "
            f"LIMIT {MAX_METRIC_ROWS}) AS sampled_rows"
        )
    return f"SELECT COUNT(*) FROM {table_ref}"


def _distinct_expression(
    source_connector: Any,
    column: dict[str, Any],
    column_ref: str,
) -> str:
    """Convert non-comparable source types before DISTINCT operations."""
    vendor = _vendor(source_connector)
    native_data_type = str(
        column.get("native_data_type")
        or column.get("data_type")
        or ""
    ).strip().lower()
    base_data_type = native_data_type.split("(", 1)[0].strip()

    if vendor == "POSTGRESQL" and base_data_type in {"json", "jsonb"}:
        return column_ref

    if vendor == "ORACLE":
        if base_data_type == "blob":
            return (
                "RAWTOHEX(DBMS_LOB.SUBSTR("
                f"{column_ref}, 2000, 1))"
            )

        if base_data_type in {"clob", "nclob"}:
            return (
                "DBMS_LOB.SUBSTR("
                f"{column_ref}, 4000, 1)"
                ")"
            )

    if vendor == "SQL_SERVER":
        if base_data_type in {
            "text",
            "ntext",
            "xml",
            "geography",
            "geometry",
            "hierarchyid",
            "sql_variant",
        }:
            return f"CONVERT(NVARCHAR(4000), {column_ref})"

        if base_data_type == "image":
            return f"CONVERT(VARCHAR(8000), {column_ref}, 1)"

    return column_ref


def _distinct_count_is_approximate(
    source_connector: Any,
    column: dict[str, Any],
) -> bool:
    """Return whether DISTINCT uses a truncated comparable value."""
    if _vendor(source_connector) != "ORACLE":
        return False

    native_data_type = str(
        column.get("native_data_type")
        or column.get("data_type")
        or ""
    ).strip().lower()
    base_data_type = native_data_type.split("(", 1)[0].strip()

    return base_data_type in {
        "blob",
        "clob",
        "nclob",
    }


def _sample_values(
    source_connector: Any,
    table_ref: str,
    column_ref: str,
    sample_expression: str,
    is_json_column: bool = False,
    timeout_deadline: float | None = None,
) -> tuple[list[Any], bool]:
    """Return distinct non-null sample values."""
    vendor = _vendor(source_connector)

    if is_json_column and vendor == "POSTGRESQL":
        query = (
            f"SELECT SUBSTRING({column_ref}::text FROM 1 FOR 100) "
            f"FROM {table_ref} WHERE {column_ref} IS NOT NULL "
            f"LIMIT {MAX_SAMPLE_VALUES}"
        )
    elif vendor == "POSTGRESQL":
        query = (
            "SELECT DISTINCT sampled_value FROM ("
            f"SELECT {sample_expression} AS sampled_value "
            f"FROM {table_ref} WHERE {column_ref} IS NOT NULL "
            f"LIMIT {MAX_METRIC_ROWS}) AS sample_candidates "
            f"LIMIT {MAX_SAMPLE_VALUES}"
        )
    elif vendor == "SQL_SERVER":
        query = (
            f"SELECT DISTINCT TOP {MAX_SAMPLE_VALUES} "
            f"{sample_expression} FROM {table_ref} "
            f"WHERE {column_ref} IS NOT NULL"
        )
    elif vendor == "ORACLE":
        query = (
            f"SELECT DISTINCT {sample_expression} FROM {table_ref} "
            f"WHERE {column_ref} IS NOT NULL "
            f"FETCH FIRST {MAX_SAMPLE_VALUES} ROWS ONLY"
        )
    else:
        query = (
            f"SELECT DISTINCT {sample_expression} FROM {table_ref} "
            f"WHERE {column_ref} IS NOT NULL "
            f"LIMIT {MAX_SAMPLE_VALUES}"
        )

    try:
        with _query_transaction(source_connector):
            cursor = _profiling_cursor(source_connector)
            try:
                _set_postgresql_sampling_timeout(
                    source_connector,
                    cursor,
                    timeout_deadline=timeout_deadline,
                )
                cursor.execute(query)
                rows = cursor.fetchall()
            finally:
                cursor.close()
    except Exception as error:
        if not _is_database_sampling_error(error):
            raise
        logger.warning(
            "Column sampling timed out; continuing without sample values",
            extra={
                "column": column_ref,
                "error_type": error.__class__.__name__,
            },
        )
        return [], True

    return [row[0] for row in rows], False


def _is_postgresql_json_column(
    source_connector: Any,
    column: dict[str, Any],
) -> bool:
    if _vendor(source_connector) != "POSTGRESQL":
        return False
    data_type = str(
        column.get("native_data_type") or column.get("data_type") or ""
    ).strip().lower()
    return data_type.split("(", 1)[0].strip() in {"json", "jsonb"}


def _is_database_sampling_error(error: Exception) -> bool:
    timeout_type_names = {
        "QueryCanceled",
        "OperationalError",
        "DBAPIError",
    }
    timeout_messages = ("timeout", "timed out", "canceling statement")
    current: BaseException | None = error
    while current is not None:
        if current.__class__.__name__ in timeout_type_names:
            return True
        message = str(current).lower()
        if any(token in message for token in timeout_messages):
            return True
        current = current.__cause__ or current.__context__
    return False


def _scalar(
    source_connector: Any,
    query: str,
    timeout_deadline: float | None = None,
):
    with _query_transaction(source_connector):
        cursor = _profiling_cursor(source_connector)
        try:
            _set_postgresql_sampling_timeout(
                source_connector,
                cursor,
                timeout_deadline=timeout_deadline,
            )
            cursor.execute(query)
            row = cursor.fetchone()
        finally:
            cursor.close()
    return int(row[0]) if row else 0


def _set_postgresql_sampling_timeout(
    source_connector: Any,
    cursor: Any,
    timeout_deadline: float | None = None,
) -> None:
    if _vendor(source_connector) == "POSTGRESQL":
        timeout_ms = 5000
        if timeout_deadline is not None:
            remaining_ms = int((timeout_deadline - monotonic()) * 1000)
            if remaining_ms <= 0:
                raise TimeoutError("Column profiling exceeded 5.0 seconds")
            timeout_ms = min(timeout_ms, remaining_ms)
        cursor.execute(
            f"SET LOCAL statement_timeout = '{timeout_ms}ms'"
        )


def _query_transaction(source_connector: Any):
    """Use a savepoint for PostgreSQL samples so query errors are recoverable."""
    if source_connector.__class__.__name__ == "PostgreSQLConnector":
        return source_connector.connection.transaction()
    return nullcontext()


def _profiling_cursor(source_connector: Any):
    cursor = source_connector.connection.cursor()
    if source_connector.__class__.__name__ == "SQLServerConnector":
        cursor.timeout = 30
    return cursor


def _vendor(source_connector: Any):
    class_name = source_connector.__class__.__name__
    mapping = {
        "PostgreSQLConnector": "POSTGRESQL",
        "MySQLConnector": "MYSQL",
        "SQLServerConnector": "SQL_SERVER",
        "OracleConnector": "ORACLE",
    }
    vendor = mapping.get(class_name)
    if vendor is None:
        raise ValueError(f"Unsupported connector class: {class_name}")
    return vendor


def _table_reference(
    source_connector: Any,
    schema_name: str,
    table_name: str,
):
    return (
        f"{_quote_identifier(source_connector, schema_name)}."
        f"{_quote_identifier(source_connector, table_name)}"
    )


def _quote_identifier(source_connector: Any, identifier: str):
    """Quote a database identifier safely, including names with spaces."""
    if not isinstance(identifier, str) or not identifier:
        raise ValueError("Database identifier must be a non-empty string")
    if "\x00" in identifier:
        raise ValueError("Database identifier contains a null character")

    vendor = _vendor(source_connector)
    if vendor == "MYSQL":
        escaped = identifier.replace("`", "``")
        return f"`{escaped}`"
    if vendor == "SQL_SERVER":
        escaped = identifier.replace("]", "]]" )
        return f"[{escaped}]"

    escaped = identifier.replace('"', '""')
    return f'"{escaped}"'


def _neighboring_columns(column, all_columns):
    selected_position = column.get("ordinal_position")
    if selected_position is None:
        return []

    neighbors = []
    for candidate in all_columns:
        position = candidate.get("ordinal_position")
        name = candidate.get("column_name")
        if position is None or name is None:
            continue
        if name == column.get("column_name"):
            continue
        if abs(position - selected_position) <= 2:
            neighbors.append(name)
    return neighbors


def mask_sample(value: Any, classification=None):
    """Mask values before persistence or classification."""
    del classification
    if value is None:
        return ""
    text = str(value)
    if not text:
        return ""
    if len(text) <= 2:
        return "*" * len(text)
    return text[0] + "*" * (len(text) - 2) + text[-1]
