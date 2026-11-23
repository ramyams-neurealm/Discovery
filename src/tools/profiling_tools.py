# # from __future__ import annotations

# # import re
# # from typing import Any

# # from src.utils.data_type_utils import classify_data_type


# # MAX_SAMPLE_VALUES = 3
# # _VALID_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_$#]*$")


# # def profile_tables(
# #     source_connector: Any,
# #     objects: list[dict[str, Any]],
# # ):
# #     """Profile tables and report the exact object when profiling fails."""
# #     table_profiles: list[dict[str, Any]] = []
# #     column_profiles: list[dict[str, Any]] = []

# #     for database_object in objects:
# #         if database_object.get("object_type") != "TABLE":
# #             continue

# #         schema_name = database_object["schema_name"]
# #         table_name = database_object["object_name"]
# #         columns = database_object.get("columns", [])

# #         try:
# #             row_count = _scalar(
# #                 source_connector,
# #                 _row_count_query(
# #                     source_connector,
# #                     schema_name,
# #                     table_name,
# #                 ),
# #             )
# #         except Exception as error:
# #             raise RuntimeError(
# #                 "Table row-count profiling failed for "
# #                 f"{schema_name}.{table_name}. "
# #                 f"Failure type: {error.__class__.__name__}. "
# #                 f"Driver message: {error}"
# #             ) from error

# #         current_profiles: list[dict[str, Any]] = []

# #         for column in columns:
# #             try:
# #                 profile = _profile_column(
# #                     source_connector=source_connector,
# #                     schema_name=schema_name,
# #                     table_name=table_name,
# #                     row_count=row_count,
# #                     column=column,
# #                     all_columns=columns,
# #                 )
# #             except Exception as error:
# #                 raise RuntimeError(
# #                     "Column profiling failed for "
# #                     f"{schema_name}.{table_name}."
# #                     f"{column.get('column_name')}. "
# #                     f"Data type: {column.get('data_type')}. "
# #                     "Native data type: "
# #                     f"{column.get('native_data_type')}. "
# #                     f"Failure type: {error.__class__.__name__}. "
# #                     f"Driver message: {error}"
# #                 ) from error

# #             current_profiles.append(profile)
# #             column_profiles.append(profile)

# #         numeric_column_count = sum(
# #             1
# #             for profile in current_profiles
# #             if (
# #                 profile.get("profile_metadata", {}).get(
# #                     "data_type_family"
# #                 )
# #                 == "NUMERIC"
# #             )
# #         )
# #         other_column_count = sum(
# #             1
# #             for profile in current_profiles
# #             if (
# #                 profile.get("profile_metadata", {}).get(
# #                     "data_type_family"
# #                 )
# #                 == "OTHER"
# #             )
# #         )
# #         categorical_column_count = (
# #             len(columns)
# #             - numeric_column_count
# #             - other_column_count
# #         )

# #         duplicate_row_count = _duplicate_row_count(
# #             source_connector=source_connector,
# #             schema_name=schema_name,
# #             table_name=table_name,
# #             columns=columns,
# #         )

# #         duplicate_row_percentage = (
# #             0.0
# #             if row_count == 0
# #             else round(
# #                 (duplicate_row_count / row_count) * 100,
# #                 4,
# #             )
# #         )

# #         percentages = [
# #             profile["null_percentage"]
# #             for profile in current_profiles
# #             if profile.get("null_percentage") is not None
# #         ]
# #         average_null = (
# #             round(sum(percentages) / len(percentages), 4)
# #             if percentages
# #             else 0.0
# #         )

# #         table_profiles.append(
# #             {
# #                 "object_id": database_object["object_id"],
# #                 "schema_name": schema_name,
# #                 "table_name": table_name,
# #                 "row_count": row_count,
# #                 "column_count": len(columns),
# #                 "average_null_percentage": average_null,
# #                 "profiling_method": "EXACT",
# #                 "profile_metadata": {
# #                     "database_vendor": _vendor(source_connector),
# #                     "numeric_column_count": numeric_column_count,
# #                     "categorical_column_count": (
# #                         categorical_column_count
# #                     ),
# #                     "other_column_count": other_column_count,
# #                                         "duplicate_row_count": duplicate_row_count,
# #                     "duplicate_row_percentage": (
# #                         duplicate_row_percentage
# #                     ),
# #                     "duplicate_row_count_is_approximate": False,
# #                 },
# #             }
# #         )

# #     return table_profiles, column_profiles


# # def _profile_column(
# #     source_connector: Any,
# #     schema_name: str,
# #     table_name: str,
# #     row_count: int,
# #     column: dict[str, Any],
# #     all_columns: list[dict[str, Any]],
# # ):
# #     column_name = column["column_name"]
# #     data_type_family = classify_data_type(
# #         column.get("data_type")
# #     )
# #     table_ref = _table_reference(
# #         source_connector,
# #         schema_name,
# #         table_name,
# #     )
# #     column_ref = _quote_identifier(source_connector, column_name)
# #     comparable_expression = _distinct_expression(
# #         source_connector=source_connector,
# #         column=column,
# #         column_ref=column_ref,
# #     )
# #     distinct_count_is_approximate = (
# #         _distinct_count_is_approximate(
# #             source_connector=source_connector,
# #             column=column,
# #         )
# #     )

# #     null_count = _scalar(
# #         source_connector,
# #         f"SELECT COUNT(*) FROM {table_ref} "
# #         f"WHERE {column_ref} IS NULL",
# #     )
# #     distinct_count = _scalar(
# #         source_connector,
# #         f"SELECT COUNT(DISTINCT {comparable_expression}) "
# #         f"FROM {table_ref} WHERE {column_ref} IS NOT NULL",
# #     )

# #     mean = None

# #     if data_type_family == "NUMERIC":
# #         mean = _decimal_scalar(
# #             source_connector,
# #             f"SELECT AVG({column_ref}) "
# #             f"FROM {table_ref} "
# #             f"WHERE {column_ref} IS NOT NULL",
# #         )
# #     raw_samples = _sample_values(
# #         source_connector=source_connector,
# #         table_ref=table_ref,
# #         column_ref=column_ref,
# #         sample_expression=comparable_expression,
# #     )

# #     null_percentage = (
# #         0.0
# #         if row_count == 0
# #         else round((null_count / row_count) * 100, 4)
# #     )
# #     masked_samples = [mask_sample(value) for value in raw_samples]

# #     return {
# #         "column_id": column["column_id"],
# #         "object_id": column["object_id"],
# #         "schema_name": schema_name,
# #         "table_name": table_name,
# #         "column_name": column_name,
# #         "data_type": column["data_type"],
# #         "nullable": column.get("nullable"),
# #         "is_primary_key": column.get("is_primary_key", False),
# #         "is_foreign_key": column.get("is_foreign_key", False),
# #         "neighboring_columns": _neighboring_columns(column, all_columns),
# #         "null_percentage": null_percentage,
# #         "distinct_count": distinct_count,
# #         "distinct_count_is_approximate": (
# #             distinct_count_is_approximate
# #         ),
# #         "masked_samples": masked_samples,
# #         "profile_metadata": {
# #             "null_count": null_count,
# #             "sample_count": len(masked_samples),
# #             "database_vendor": _vendor(source_connector),
# #             "data_type_family": data_type_family,
# #             "mean": mean,
# #         },
# #     }


# # def _row_count_query(
# #     source_connector: Any,
# #     schema_name: str,
# #     table_name: str,
# # ):
# #     table_ref = _table_reference(
# #         source_connector,
# #         schema_name,
# #         table_name,
# #     )
# #     return f"SELECT COUNT(*) FROM {table_ref}"

# # def _duplicate_row_count(
# #     source_connector: Any,
# #     schema_name: str,
# #     table_name: str,
# #     columns: list[dict[str, Any]],
# # ) -> int:
# #     """Count rows that duplicate another complete table row."""
# #     if not columns:
# #         return 0

# #     table_ref = _table_reference(
# #         source_connector,
# #         schema_name,
# #         table_name,
# #     )

# #     comparable_columns = []

# #     for column in columns:
# #         column_ref = _quote_identifier(
# #             source_connector,
# #             column["column_name"],
# #         )
# #         comparable_columns.append(
# #             _distinct_expression(
# #                 source_connector=source_connector,
# #                 column=column,
# #                 column_ref=column_ref,
# #             )
# #         )

# #     group_by_columns = ", ".join(comparable_columns)

# #     query = (
# #         "SELECT COALESCE(SUM(duplicate_count - 1), 0) "
# #         "FROM ("
# #         "SELECT COUNT(*) AS duplicate_count "
# #         f"FROM {table_ref} "
# #         f"GROUP BY {group_by_columns} "
# #         "HAVING COUNT(*) > 1"
# #         ") AS duplicate_groups"
# #     )

# #     return _scalar(source_connector, query)

# # def _distinct_expression(
# #     source_connector: Any,
# #     column: dict[str, Any],
# #     column_ref: str,
# # ) -> str:
# #     """Convert non-comparable source types before DISTINCT operations."""
# #     vendor = _vendor(source_connector)
# #     native_data_type = str(
# #         column.get("native_data_type")
# #         or column.get("data_type")
# #         or ""
# #     ).strip().lower()
# #     base_data_type = native_data_type.split("(", 1)[0].strip()

# #     if vendor == "POSTGRESQL" and base_data_type == "json":
# #         return f"CAST({column_ref} AS TEXT)"

# #     if vendor == "ORACLE":
# #         if base_data_type == "blob":
# #             return (
# #                 "RAWTOHEX(DBMS_LOB.SUBSTR("
# #                 f"{column_ref}, 2000, 1))"
# #             )

# #         if base_data_type in {"clob", "nclob"}:
# #             return (
# #                 "DBMS_LOB.SUBSTR("
# #                 f"{column_ref}, 4000, 1)"
# #                 ")"
# #             )

# #     if vendor == "SQL_SERVER":
# #         if base_data_type in {
# #             "text",
# #             "ntext",
# #             "xml",
# #             "geography",
# #             "geometry",
# #             "hierarchyid",
# #             "sql_variant",
# #         }:
# #             return f"CONVERT(NVARCHAR(4000), {column_ref})"

# #         if base_data_type == "image":
# #             return f"CONVERT(VARCHAR(8000), {column_ref}, 1)"

# #     return column_ref


# # def _distinct_count_is_approximate(
# #     source_connector: Any,
# #     column: dict[str, Any],
# # ) -> bool:
# #     """Return whether DISTINCT uses a truncated comparable value."""
# #     if _vendor(source_connector) != "ORACLE":
# #         return False

# #     native_data_type = str(
# #         column.get("native_data_type")
# #         or column.get("data_type")
# #         or ""
# #     ).strip().lower()
# #     base_data_type = native_data_type.split("(", 1)[0].strip()

# #     return base_data_type in {
# #         "blob",
# #         "clob",
# #         "nclob",
# #     }


# # def _sample_values(
# #     source_connector: Any,
# #     table_ref: str,
# #     column_ref: str,
# #     sample_expression: str,
# # ):
# #     """Return distinct non-null sample values."""
# #     vendor = _vendor(source_connector)

# #     if vendor == "SQL_SERVER":
# #         query = (
# #             f"SELECT DISTINCT TOP {MAX_SAMPLE_VALUES} "
# #             f"{sample_expression} FROM {table_ref} "
# #             f"WHERE {column_ref} IS NOT NULL"
# #         )
# #     elif vendor == "ORACLE":
# #         query = (
# #             f"SELECT DISTINCT {sample_expression} FROM {table_ref} "
# #             f"WHERE {column_ref} IS NOT NULL "
# #             f"FETCH FIRST {MAX_SAMPLE_VALUES} ROWS ONLY"
# #         )
# #     else:
# #         query = (
# #             f"SELECT DISTINCT {sample_expression} FROM {table_ref} "
# #             f"WHERE {column_ref} IS NOT NULL "
# #             f"LIMIT {MAX_SAMPLE_VALUES}"
# #         )

# #     cursor = source_connector.connection.cursor()
# #     try:
# #         cursor.execute(query)
# #         rows = cursor.fetchall()
# #     finally:
# #         cursor.close()

# #     return [row[0] for row in rows]


# # def _scalar(source_connector: Any, query: str):
# #     cursor = source_connector.connection.cursor()
# #     try:
# #         cursor.execute(query)
# #         row = cursor.fetchone()
# #     finally:
# #         cursor.close()
# #     return int(row[0]) if row else 0

# # def _decimal_scalar(
# #     source_connector: Any,
# #     query: str,
# # ) -> float | None:
# #     """Execute a scalar query and return a rounded decimal value."""
# #     cursor = source_connector.connection.cursor()

# #     try:
# #         cursor.execute(query)
# #         row = cursor.fetchone()
# #     finally:
# #         cursor.close()

# #     if row is None or row[0] is None:
# #         return None

# #     return round(float(row[0]), 4)


# # def _vendor(source_connector: Any):
# #     class_name = source_connector.__class__.__name__
# #     mapping = {
# #         "PostgreSQLConnector": "POSTGRESQL",
# #         "MySQLConnector": "MYSQL",
# #         "SQLServerConnector": "SQL_SERVER",
# #         "OracleConnector": "ORACLE",
# #     }
# #     vendor = mapping.get(class_name)
# #     if vendor is None:
# #         raise ValueError(f"Unsupported connector class: {class_name}")
# #     return vendor


# # def _table_reference(
# #     source_connector: Any,
# #     schema_name: str,
# #     table_name: str,
# # ):
# #     return (
# #         f"{_quote_identifier(source_connector, schema_name)}."
# #         f"{_quote_identifier(source_connector, table_name)}"
# #     )


# # def _quote_identifier(source_connector: Any, identifier: str):
# #     """Quote a database identifier safely, including names with spaces."""
# #     if not isinstance(identifier, str) or not identifier:
# #         raise ValueError("Database identifier must be a non-empty string")
# #     if "\x00" in identifier:
# #         raise ValueError("Database identifier contains a null character")

# #     vendor = _vendor(source_connector)
# #     if vendor == "MYSQL":
# #         escaped = identifier.replace("`", "``")
# #         return f"`{escaped}`"
# #     if vendor == "SQL_SERVER":
# #         escaped = identifier.replace("]", "]]" )
# #         return f"[{escaped}]"

# #     escaped = identifier.replace('"', '""')
# #     return f'"{escaped}"'


# # def _neighboring_columns(column, all_columns):
# #     selected_position = column.get("ordinal_position")
# #     if selected_position is None:
# #         return []

# #     neighbors = []
# #     for candidate in all_columns:
# #         position = candidate.get("ordinal_position")
# #         name = candidate.get("column_name")
# #         if position is None or name is None:
# #             continue
# #         if name == column.get("column_name"):
# #             continue
# #         if abs(position - selected_position) <= 2:
# #             neighbors.append(name)
# #     return neighbors


# # def mask_sample(value: Any, classification=None):
# #     """Mask values before persistence or classification."""
# #     del classification
# #     if value is None:
# #         return ""
# #     text = str(value)
# #     if not text:
# #         return ""
# #     if len(text) <= 2:
# #         return "*" * len(text)
# #     return text[0] + "*" * (len(text) - 2) + text[-1]










# from __future__ import annotations

# import re
# from typing import Any

# from src.utils.data_type_utils import classify_data_type


# MAX_SAMPLE_VALUES = 3
# _VALID_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_$#]*$")
# _ISO_TIMESTAMP_RE = re.compile(r"^(\d{4})-\d{2}-\d{2}[T ]\d{2}:\d{2}")
# _ISO_DATE_RE = re.compile(r"^(\d{4})-\d{2}-\d{2}$")
# _EMAIL_RE = re.compile(r"^([^@\s])[^@\s]*@([^@\s]+\.[^@\s]+)$")
# _DECIMAL_RE = re.compile(r"^(-?\d+)\.(\d+)$")


# def profile_tables(
#     source_connector: Any,
#     objects: list[dict[str, Any]],
# ):
#     """Profile tables and report the exact object when profiling fails."""
#     table_profiles: list[dict[str, Any]] = []
#     column_profiles: list[dict[str, Any]] = []

#     for database_object in objects:
#         if database_object.get("object_type") != "TABLE":
#             continue

#         schema_name = database_object["schema_name"]
#         table_name = database_object["object_name"]
#         columns = database_object.get("columns", [])

#         try:
#             row_count = _scalar(
#                 source_connector,
#                 _row_count_query(
#                     source_connector,
#                     schema_name,
#                     table_name,
#                 ),
#             )
#         except Exception as error:
#             raise RuntimeError(
#                 "Table row-count profiling failed for "
#                 f"{schema_name}.{table_name}. "
#                 f"Failure type: {error.__class__.__name__}. "
#                 f"Driver message: {error}"
#             ) from error

#         current_profiles: list[dict[str, Any]] = []

#         for column in columns:
#             try:
#                 profile = _profile_column(
#                     source_connector=source_connector,
#                     schema_name=schema_name,
#                     table_name=table_name,
#                     row_count=row_count,
#                     column=column,
#                     all_columns=columns,
#                 )
#             except Exception as error:
#                 raise RuntimeError(
#                     "Column profiling failed for "
#                     f"{schema_name}.{table_name}."
#                     f"{column.get('column_name')}. "
#                     f"Data type: {column.get('data_type')}. "
#                     "Native data type: "
#                     f"{column.get('native_data_type')}. "
#                     f"Failure type: {error.__class__.__name__}. "
#                     f"Driver message: {error}"
#                 ) from error

#             current_profiles.append(profile)
#             column_profiles.append(profile)

#         numeric_column_count = sum(
#             1
#             for profile in current_profiles
#             if (
#                 profile.get("profile_metadata", {}).get(
#                     "data_type_family"
#                 )
#                 == "NUMERIC"
#             )
#         )
#         other_column_count = sum(
#             1
#             for profile in current_profiles
#             if (
#                 profile.get("profile_metadata", {}).get(
#                     "data_type_family"
#                 )
#                 == "OTHER"
#             )
#         )
#         categorical_column_count = (
#             len(columns)
#             - numeric_column_count
#             - other_column_count
#         )

#         duplicate_row_count = _duplicate_row_count(
#             source_connector=source_connector,
#             schema_name=schema_name,
#             table_name=table_name,
#             columns=columns,
#         )

#         duplicate_row_percentage = (
#             0.0
#             if row_count == 0
#             else round(
#                 (duplicate_row_count / row_count) * 100,
#                 4,
#             )
#         )

#         percentages = [
#             profile["null_percentage"]
#             for profile in current_profiles
#             if profile.get("null_percentage") is not None
#         ]
#         average_null = (
#             round(sum(percentages) / len(percentages), 4)
#             if percentages
#             else 0.0
#         )

#         table_profiles.append(
#             {
#                 "object_id": database_object["object_id"],
#                 "schema_name": schema_name,
#                 "table_name": table_name,
#                 "row_count": row_count,
#                 "column_count": len(columns),
#                 "average_null_percentage": average_null,
#                 "profiling_method": "EXACT",
#                 "profile_metadata": {
#                     "database_vendor": _vendor(source_connector),
#                     "numeric_column_count": numeric_column_count,
#                     "categorical_column_count": (
#                         categorical_column_count
#                     ),
#                     "other_column_count": other_column_count,
#                     "duplicate_row_count": duplicate_row_count,
#                     "duplicate_row_percentage": (
#                         duplicate_row_percentage
#                     ),
#                     "duplicate_row_count_is_approximate": False,
#                 },
#             }
#         )

#     return table_profiles, column_profiles


# def _profile_column(
#     source_connector: Any,
#     schema_name: str,
#     table_name: str,
#     row_count: int,
#     column: dict[str, Any],
#     all_columns: list[dict[str, Any]],
# ):
#     column_name = column["column_name"]
#     data_type_family = classify_data_type(
#         column.get("data_type")
#     )
#     table_ref = _table_reference(
#         source_connector,
#         schema_name,
#         table_name,
#     )
#     column_ref = _quote_identifier(source_connector, column_name)
#     comparable_expression = _distinct_expression(
#         source_connector=source_connector,
#         column=column,
#         column_ref=column_ref,
#     )
#     distinct_count_is_approximate = (
#         _distinct_count_is_approximate(
#             source_connector=source_connector,
#             column=column,
#         )
#     )

#     null_count = _scalar(
#         source_connector,
#         f"SELECT COUNT(*) FROM {table_ref} "
#         f"WHERE {column_ref} IS NULL",
#     )
#     distinct_count = _scalar(
#         source_connector,
#         f"SELECT COUNT(DISTINCT {comparable_expression}) "
#         f"FROM {table_ref} WHERE {column_ref} IS NOT NULL",
#     )

#     mean = None

#     if data_type_family == "NUMERIC":
#         mean = _decimal_scalar(
#             source_connector,
#             f"SELECT AVG({column_ref}) "
#             f"FROM {table_ref} "
#             f"WHERE {column_ref} IS NOT NULL",
#         )
#     raw_samples = _sample_values(
#         source_connector=source_connector,
#         table_ref=table_ref,
#         column_ref=column_ref,
#         sample_expression=comparable_expression,
#     )

#     null_percentage = (
#         0.0
#         if row_count == 0
#         else round((null_count / row_count) * 100, 4)
#     )
#     masked_samples = [mask_sample(value) for value in raw_samples]

#     return {
#         "column_id": column["column_id"],
#         "object_id": column["object_id"],
#         "schema_name": schema_name,
#         "table_name": table_name,
#         "column_name": column_name,
#         "data_type": column["data_type"],
#         "nullable": column.get("nullable"),
#         "is_primary_key": column.get("is_primary_key", False),
#         "is_foreign_key": column.get("is_foreign_key", False),
#         "neighboring_columns": _neighboring_columns(column, all_columns),
#         "null_percentage": null_percentage,
#         "distinct_count": distinct_count,
#         "distinct_count_is_approximate": (
#             distinct_count_is_approximate
#         ),
#         "masked_samples": masked_samples,
#         "profile_metadata": {
#             "null_count": null_count,
#             "sample_count": len(masked_samples),
#             "database_vendor": _vendor(source_connector),
#             "data_type_family": data_type_family,
#             "mean": mean,
#         },
#     }


# def _row_count_query(
#     source_connector: Any,
#     schema_name: str,
#     table_name: str,
# ):
#     table_ref = _table_reference(
#         source_connector,
#         schema_name,
#         table_name,
#     )
#     return f"SELECT COUNT(*) FROM {table_ref}"


# def _duplicate_row_count(
#     source_connector: Any,
#     schema_name: str,
#     table_name: str,
#     columns: list[dict[str, Any]],
# ) -> int:
#     """Count rows that duplicate another complete table row."""
#     if not columns:
#         return 0

#     table_ref = _table_reference(
#         source_connector,
#         schema_name,
#         table_name,
#     )

#     comparable_columns = []

#     for column in columns:
#         column_ref = _quote_identifier(
#             source_connector,
#             column["column_name"],
#         )
#         comparable_columns.append(
#             _distinct_expression(
#                 source_connector=source_connector,
#                 column=column,
#                 column_ref=column_ref,
#             )
#         )

#     group_by_columns = ", ".join(comparable_columns)

#     query = (
#         "SELECT COALESCE(SUM(duplicate_count - 1), 0) "
#         "FROM ("
#         "SELECT COUNT(*) AS duplicate_count "
#         f"FROM {table_ref} "
#         f"GROUP BY {group_by_columns} "
#         "HAVING COUNT(*) > 1"
#         ") AS duplicate_groups"
#     )

#     return _scalar(source_connector, query)


# def _distinct_expression(
#     source_connector: Any,
#     column: dict[str, Any],
#     column_ref: str,
# ) -> str:
#     """Convert non-comparable source types before DISTINCT operations."""
#     vendor = _vendor(source_connector)
#     native_data_type = str(
#         column.get("native_data_type")
#         or column.get("data_type")
#         or ""
#     ).strip().lower()
#     base_data_type = native_data_type.split("(", 1)[0].strip()

#     if vendor == "POSTGRESQL" and base_data_type == "json":
#         return f"CAST({column_ref} AS TEXT)"

#     if vendor == "ORACLE":
#         if base_data_type == "blob":
#             return (
#                 "RAWTOHEX(DBMS_LOB.SUBSTR("
#                 f"{column_ref}, 2000, 1))"
#             )

#         if base_data_type in {"clob", "nclob"}:
#             return (
#                 "DBMS_LOB.SUBSTR("
#                 f"{column_ref}, 4000, 1)"
#             )

#     if vendor == "SQL_SERVER":
#         if base_data_type in {
#             "text",
#             "ntext",
#             "xml",
#             "geography",
#             "geometry",
#             "hierarchyid",
#             "sql_variant",
#         }:
#             return f"CONVERT(NVARCHAR(4000), {column_ref})"

#         if base_data_type == "image":
#             return f"CONVERT(VARCHAR(8000), {column_ref}, 1)"

#     return column_ref


# def _distinct_count_is_approximate(
#     source_connector: Any,
#     column: dict[str, Any],
# ) -> bool:
#     """Return whether DISTINCT uses a truncated comparable value."""
#     if _vendor(source_connector) != "ORACLE":
#         return False

#     native_data_type = str(
#         column.get("native_data_type")
#         or column.get("data_type")
#         or ""
#     ).strip().lower()
#     base_data_type = native_data_type.split("(", 1)[0].strip()

#     return base_data_type in {
#         "blob",
#         "clob",
#         "nclob",
#     }


# def _sample_values(
#     source_connector: Any,
#     table_ref: str,
#     column_ref: str,
#     sample_expression: str,
# ):
#     """Return distinct non-null sample values."""
#     vendor = _vendor(source_connector)

#     if vendor == "SQL_SERVER":
#         query = (
#             f"SELECT DISTINCT TOP {MAX_SAMPLE_VALUES} "
#             f"{sample_expression} FROM {table_ref} "
#             f"WHERE {column_ref} IS NOT NULL"
#         )
#     elif vendor == "ORACLE":
#         query = (
#             f"SELECT DISTINCT {sample_expression} FROM {table_ref} "
#             f"WHERE {column_ref} IS NOT NULL "
#             f"FETCH FIRST {MAX_SAMPLE_VALUES} ROWS ONLY"
#         )
#     else:
#         query = (
#             f"SELECT DISTINCT {sample_expression} FROM {table_ref} "
#             f"WHERE {column_ref} IS NOT NULL "
#             f"LIMIT {MAX_SAMPLE_VALUES}"
#         )

#     cursor = source_connector.connection.cursor()
#     try:
#         cursor.execute(query)
#         rows = cursor.fetchall()
#     finally:
#         cursor.close()

#     return [row[0] for row in rows]


# def _scalar(source_connector: Any, query: str):
#     cursor = source_connector.connection.cursor()
#     try:
#         cursor.execute(query)
#         row = cursor.fetchone()
#     finally:
#         cursor.close()
#     return int(row[0]) if row else 0


# def _decimal_scalar(
#     source_connector: Any,
#     query: str,
# ) -> float | None:
#     """Execute a scalar query and return a rounded decimal value."""
#     cursor = source_connector.connection.cursor()

#     try:
#         cursor.execute(query)
#         row = cursor.fetchone()
#     finally:
#         cursor.close()

#     if row is None or row[0] is None:
#         return None

#     return round(float(row[0]), 4)


# def _vendor(source_connector: Any):
#     class_name = source_connector.__class__.__name__
#     mapping = {
#         "PostgreSQLConnector": "POSTGRESQL",
#         "MySQLConnector": "MYSQL",
#         "SQLServerConnector": "SQL_SERVER",
#         "OracleConnector": "ORACLE",
#     }
#     vendor = mapping.get(class_name)
#     if vendor is None:
#         raise ValueError(f"Unsupported connector class: {class_name}")
#     return vendor


# def _table_reference(
#     source_connector: Any,
#     schema_name: str,
#     table_name: str,
# ):
#     return (
#         f"{_quote_identifier(source_connector, schema_name)}."
#         f"{_quote_identifier(source_connector, table_name)}"
#     )


# def _quote_identifier(source_connector: Any, identifier: str):
#     """Quote a database identifier safely, including names with spaces."""
#     if not isinstance(identifier, str) or not identifier:
#         raise ValueError("Database identifier must be a non-empty string")
#     if "\x00" in identifier:
#         raise ValueError("Database identifier contains a null character")

#     vendor = _vendor(source_connector)
#     if vendor == "MYSQL":
#         escaped = identifier.replace("`", "``")
#         return f"`{escaped}`"
#     if vendor == "SQL_SERVER":
#         escaped = identifier.replace("]", "]]")
#         return f"[{escaped}]"

#     escaped = identifier.replace('"', '""')
#     return f'"{escaped}"'


# def _neighboring_columns(column, all_columns):
#     selected_position = column.get("ordinal_position")
#     if selected_position is None:
#         return []

#     neighbors = []
#     for candidate in all_columns:
#         position = candidate.get("ordinal_position")
#         name = candidate.get("column_name")
#         if position is None or name is None:
#             continue
#         if name == column.get("column_name"):
#             continue
#         if abs(position - selected_position) <= 2:
#             neighbors.append(name)
#     return neighbors


# def mask_sample(value: Any, classification=None) -> str:
#     """Format-preserving, fixed-width masking for UI display and LLM classification."""
#     del classification
#     if value is None:
#         return ""

#     text = str(value).strip()
#     if not text:
#         return ""

#     # 1. Timestamps & dates -> "2026-**-** **:**" or "2026-**-**"
#     ts_match = _ISO_TIMESTAMP_RE.match(text)
#     if ts_match:
#         return f"{ts_match.group(1)}-**-** **:**"

#     date_match = _ISO_DATE_RE.match(text)
#     if date_match:
#         return f"{date_match.group(1)}-**-**"

#     # 2. Email addresses -> "j***@example.com"
#     email_match = _EMAIL_RE.match(text)
#     if email_match:
#         return f"{email_match.group(1)}***@{email_match.group(2)}"

#     # 3. Signed/unsigned decimals -> "1***.50" or "-1***.00"
#     dec_match = _DECIMAL_RE.match(text)
#     if dec_match:
#         int_part, frac_part = dec_match.group(1), dec_match.group(2)
#         prefix = int_part[:2] if int_part.startswith("-") else int_part[0]
#         stars = "**" if len(int_part.lstrip("-")) <= 2 else "***"
#         return f"{prefix}{stars}.{frac_part[:2]}"

#     # 4. Short 1–2 char values (e.g., ID = 5) -> "5*" instead of bare "*"
#     if len(text) <= 2:
#         return f"{text[0]}*"

#     # 5. Long free-text / multi-word strings (>16 chars) -> fixed 8-char preview "Pen*** 3"
#     if len(text) > 16:
#         return f"{text[:3]}***{text[-2:]}"

#     # 6. Standard words & IDs (3–16 chars) -> fixed 5-char mask "C***t", "7***2"
#     return f"{text[0]}***{text[-1]}"















from __future__ import annotations

import re
from typing import Any

from src.utils.data_type_utils import classify_data_type


MAX_SAMPLE_VALUES = 3
PATTERN_SCAN_SAMPLE_LIMIT = 250

_VALID_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_$#]*$")
_ISO_TIMESTAMP_RE = re.compile(r"^(\d{4})-\d{2}-\d{2}[T ]\d{2}:\d{2}")
_ISO_DATE_RE = re.compile(r"^(\d{4})-\d{2}-\d{2}$")
_EMAIL_RE = re.compile(r"^([^@\s])[^@\s]*@([^@\s]+\.[^@\s]+)$")
_DECIMAL_RE = re.compile(r"^(-?\d+)\.(\d+)$")

# Embedded / standalone pattern detectors for in-memory pre-masking scan
_SCAN_EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
_SCAN_SSN_RE = re.compile(r"\b(?!000|666|9\d{2})\d{3}-(?!00)\d{2}-(?!0000)\d{4}\b")
_SCAN_CARD_CANDIDATE_RE = re.compile(r"(?<!\d)(?:\d[ -]*?){13,19}(?!\d)")
_SCAN_AADHAAR_CANDIDATE_RE = re.compile(r"(?<!\d)[2-9]\d{3}[\s-]?\d{4}[\s-]?\d{4}(?!\d)")
_SCAN_IN_PAN_RE = re.compile(r"\b[A-Z]{3}[ABCFGHLJPTF][A-Z]\d{4}[A-Z]\b")
_SCAN_IBAN_CANDIDATE_RE = re.compile(r"\b[A-Z]{2}\d{2}[A-Z0-9]{11,30}\b")
_SCAN_PHONE_RE = re.compile(
    r"(?:(?<!\d)\+\d{1,3}[\s.-]?\(?\d{2,4}\)?[\s.-]?\d{3,4}[\s.-]?\d{4}(?!\d)"
    r"|(?<!\d)\(?\d{3}\)?[\s.-]\d{3}[\s.-]\d{4}(?!\d))"
)
_SCAN_IPV4_RE = re.compile(
    r"\b(?:(?:25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)\.){3}(?:25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)\b"
)
_SCAN_SECRET_RE = re.compile(
    r"\b(?:sk-[A-Za-z0-9_-]{20,}|AKIA[0-9A-Z]{16}|ghp_[A-Za-z0-9]{36}"
    r"|eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,})\b"
)

_VERHOEFF_D = (
    (0, 1, 2, 3, 4, 5, 6, 7, 8, 9),
    (1, 2, 3, 4, 0, 6, 7, 8, 9, 5),
    (2, 3, 4, 0, 1, 7, 8, 9, 5, 6),
    (3, 4, 0, 1, 2, 8, 9, 5, 6, 7),
    (4, 0, 1, 2, 3, 9, 5, 6, 7, 8),
    (5, 9, 8, 7, 6, 0, 4, 3, 2, 1),
    (6, 5, 9, 8, 7, 1, 0, 4, 3, 2),
    (7, 6, 5, 9, 8, 2, 1, 0, 4, 3),
    (8, 7, 6, 5, 9, 3, 2, 1, 0, 4),
    (9, 8, 7, 6, 5, 4, 3, 2, 1, 0),
)
_VERHOEFF_P = (
    (0, 1, 2, 3, 4, 5, 6, 7, 8, 9),
    (1, 5, 7, 6, 2, 8, 3, 0, 9, 4),
    (5, 8, 0, 3, 7, 9, 6, 1, 4, 2),
    (8, 9, 1, 6, 0, 4, 3, 5, 2, 7),
    (9, 4, 5, 3, 1, 2, 6, 8, 7, 0),
    (4, 2, 8, 6, 5, 7, 3, 9, 0, 1),
    (2, 7, 9, 3, 8, 0, 6, 4, 1, 5),
    (7, 0, 4, 6, 9, 1, 3, 2, 5, 8),
)


def _passes_luhn(digits: str) -> bool:
    if len(digits) < 13 or len(digits) > 19 or not digits.isdigit():
        return False
    if len(set(digits)) == 1:
        return False
    total = 0
    for idx, ch in enumerate(reversed(digits)):
        val = int(ch)
        if idx % 2 == 1:
            val *= 2
            if val > 9:
                val -= 9
        total += val
    return total % 10 == 0


def _passes_verhoeff(digits: str) -> bool:
    if len(digits) != 12 or not digits.isdigit() or digits[0] in ("0", "1"):
        return False
    if len(set(digits)) == 1:
        return False
    c = 0
    for idx, ch in enumerate(reversed(digits)):
        c = _VERHOEFF_D[c][_VERHOEFF_P[idx % 8][int(ch)]]
    return c == 0


def _passes_iban_mod97(iban: str) -> bool:
    cleaned = re.sub(r"\s+", "", iban).upper()
    if len(cleaned) < 15 or len(cleaned) > 34 or not cleaned.isalnum():
        return False
    rearranged = cleaned[4:] + cleaned[:4]
    numeric_str = "".join(
        str(ord(ch) - 55) if ch.isalpha() else ch
        for ch in rearranged
    )
    return int(numeric_str) % 97 == 1


def scan_pattern_hits(values: list[Any]) -> dict[str, float]:
    """Run deterministic regex & checksum detectors over raw values in memory.

    Returns a dictionary of {subtype: match_percentage} for any matched pattern.
    Raw values never leave this function.
    """
    texts = [str(v).strip() for v in values if v is not None and str(v).strip()]
    total = len(texts)
    if total == 0:
        return {}

    counts: dict[str, int] = {}

    for text in texts:
        matched_in_row: set[str] = set()

        if _SCAN_EMAIL_RE.search(text):
            matched_in_row.add("EMAIL_ADDRESS")

        if _SCAN_SSN_RE.search(text):
            matched_in_row.add("SSN")

        for cand in _SCAN_CARD_CANDIDATE_RE.finditer(text):
            digits = re.sub(r"\D", "", cand.group(0))
            if _passes_luhn(digits):
                matched_in_row.add("CREDIT_CARD_NUMBER")
                break

        for cand in _SCAN_AADHAAR_CANDIDATE_RE.finditer(text):
            digits = re.sub(r"\D", "", cand.group(0))
            if _passes_verhoeff(digits):
                matched_in_row.add("IN_AADHAAR")
                break

        if _SCAN_IN_PAN_RE.search(text):
            matched_in_row.add("IN_PAN")

        for cand in _SCAN_IBAN_CANDIDATE_RE.finditer(text):
            if _passes_iban_mod97(cand.group(0)):
                matched_in_row.add("IBAN")
                break

        if _SCAN_PHONE_RE.search(text):
            matched_in_row.add("PHONE_NUMBER")

        if _SCAN_IPV4_RE.search(text):
            matched_in_row.add("IP_ADDRESS")

        if _SCAN_SECRET_RE.search(text):
            matched_in_row.add("API_TOKEN")

        for subtype in matched_in_row:
            counts[subtype] = counts.get(subtype, 0) + 1

    return {
        subtype: round((hit_count / total) * 100, 2)
        for subtype, hit_count in sorted(counts.items(), key=lambda item: -item[1])
        if hit_count > 0
    }


def _should_scan_patterns(column: dict[str, Any], data_type_family: str) -> bool:
    """Return True for text, semi-structured, or integer columns that may carry sensitive patterns."""
    raw_type = str(
        column.get("native_data_type") or column.get("data_type") or ""
    ).strip().lower()
    base_type = raw_type.split("(", 1)[0].strip()

    if data_type_family == "TEXT":
        return True
    if base_type in {"json", "jsonb", "xml", "uuid"}:
        return True
    if data_type_family == "NUMERIC" and any(
        tok in base_type for tok in ("int", "bigint", "number", "numeric", "decimal")
    ):
        # Skip small integers / floating-point metrics
        if any(tok in base_type for tok in ("smallint", "tinyint", "float", "double", "real")):
            return False
        return True
    return False


def profile_tables(
    source_connector: Any,
    objects: list[dict[str, Any]],
):
    """Profile tables and report the exact object when profiling fails."""
    table_profiles: list[dict[str, Any]] = []
    column_profiles: list[dict[str, Any]] = []

    for database_object in objects:
        if database_object.get("object_type") != "TABLE":
            continue

        schema_name = database_object["schema_name"]
        table_name = database_object["object_name"]
        columns = database_object.get("columns", [])

        try:
            row_count = _scalar(
                source_connector,
                _row_count_query(
                    source_connector,
                    schema_name,
                    table_name,
                ),
            )
        except Exception as error:
            raise RuntimeError(
                "Table row-count profiling failed for "
                f"{schema_name}.{table_name}. "
                f"Failure type: {error.__class__.__name__}. "
                f"Driver message: {error}"
            ) from error

        current_profiles: list[dict[str, Any]] = []

        for column in columns:
            try:
                profile = _profile_column(
                    source_connector=source_connector,
                    schema_name=schema_name,
                    table_name=table_name,
                    row_count=row_count,
                    column=column,
                    all_columns=columns,
                )
            except Exception as error:
                raise RuntimeError(
                    "Column profiling failed for "
                    f"{schema_name}.{table_name}."
                    f"{column.get('column_name')}. "
                    f"Data type: {column.get('data_type')}. "
                    "Native data type: "
                    f"{column.get('native_data_type')}. "
                    f"Failure type: {error.__class__.__name__}. "
                    f"Driver message: {error}"
                ) from error

            current_profiles.append(profile)
            column_profiles.append(profile)

        numeric_column_count = sum(
            1
            for profile in current_profiles
            if (
                profile.get("profile_metadata", {}).get(
                    "data_type_family"
                )
                == "NUMERIC"
            )
        )
        other_column_count = sum(
            1
            for profile in current_profiles
            if (
                profile.get("profile_metadata", {}).get(
                    "data_type_family"
                )
                == "OTHER"
            )
        )
        categorical_column_count = (
            len(columns)
            - numeric_column_count
            - other_column_count
        )

        duplicate_row_count = _duplicate_row_count(
            source_connector=source_connector,
            schema_name=schema_name,
            table_name=table_name,
            columns=columns,
        )

        duplicate_row_percentage = (
            0.0
            if row_count == 0
            else round(
                (duplicate_row_count / row_count) * 100,
                4,
            )
        )

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

        table_profiles.append(
            {
                "object_id": database_object["object_id"],
                "schema_name": schema_name,
                "table_name": table_name,
                "row_count": row_count,
                "column_count": len(columns),
                "average_null_percentage": average_null,
                "profiling_method": "EXACT",
                "profile_metadata": {
                    "database_vendor": _vendor(source_connector),
                    "numeric_column_count": numeric_column_count,
                    "categorical_column_count": (
                        categorical_column_count
                    ),
                    "other_column_count": other_column_count,
                    "duplicate_row_count": duplicate_row_count,
                    "duplicate_row_percentage": (
                        duplicate_row_percentage
                    ),
                    "duplicate_row_count_is_approximate": False,
                },
            }
        )

    return table_profiles, column_profiles


def _profile_column(
    source_connector: Any,
    schema_name: str,
    table_name: str,
    row_count: int,
    column: dict[str, Any],
    all_columns: list[dict[str, Any]],
):
    column_name = column["column_name"]
    data_type_family = classify_data_type(
        column.get("data_type")
    )
    table_ref = _table_reference(
        source_connector,
        schema_name,
        table_name,
    )
    column_ref = _quote_identifier(source_connector, column_name)
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

    null_count = _scalar(
        source_connector,
        f"SELECT COUNT(*) FROM {table_ref} "
        f"WHERE {column_ref} IS NULL",
    )
    distinct_count = _scalar(
        source_connector,
        f"SELECT COUNT(DISTINCT {comparable_expression}) "
        f"FROM {table_ref} WHERE {column_ref} IS NOT NULL",
    )

    mean = None

    if data_type_family == "NUMERIC":
        mean = _decimal_scalar(
            source_connector,
            f"SELECT AVG({column_ref}) "
            f"FROM {table_ref} "
            f"WHERE {column_ref} IS NOT NULL",
        )

    pattern_hits: dict[str, float] = {}
    scanned_row_count = 0
    raw_samples: list[Any] = []

    if row_count > 0 and _should_scan_patterns(column, data_type_family):
        raw_scan_values = _scan_sample_values(
            source_connector=source_connector,
            table_ref=table_ref,
            column_ref=column_ref,
            sample_expression=comparable_expression,
            limit=PATTERN_SCAN_SAMPLE_LIMIT,
        )
        scanned_row_count = len(raw_scan_values)
        pattern_hits = scan_pattern_hits(raw_scan_values)

        # Reuse up to 3 distinct values already fetched in memory before issuing another query
        seen_keys: set[str] = set()
        for val in raw_scan_values:
            if val is None:
                continue
            key = str(val)
            if key not in seen_keys:
                seen_keys.add(key)
                raw_samples.append(val)
                if len(raw_samples) >= MAX_SAMPLE_VALUES:
                    break

    if len(raw_samples) < MAX_SAMPLE_VALUES and row_count > 0:
        raw_samples = _sample_values(
            source_connector=source_connector,
            table_ref=table_ref,
            column_ref=column_ref,
            sample_expression=comparable_expression,
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
        "pattern_hits": pattern_hits,
        "table_row_count": row_count,
        "profile_metadata": {
            "null_count": null_count,
            "sample_count": len(masked_samples),
            "database_vendor": _vendor(source_connector),
            "data_type_family": data_type_family,
            "mean": mean,
            "pattern_hits": pattern_hits,
            "pattern_scan_sample_size": scanned_row_count,
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
    return f"SELECT COUNT(*) FROM {table_ref}"


def _duplicate_row_count(
    source_connector: Any,
    schema_name: str,
    table_name: str,
    columns: list[dict[str, Any]],
) -> int:
    """Count rows that duplicate another complete table row."""
    if not columns:
        return 0

    table_ref = _table_reference(
        source_connector,
        schema_name,
        table_name,
    )

    comparable_columns = []

    for column in columns:
        column_ref = _quote_identifier(
            source_connector,
            column["column_name"],
        )
        comparable_columns.append(
            _distinct_expression(
                source_connector=source_connector,
                column=column,
                column_ref=column_ref,
            )
        )

    group_by_columns = ", ".join(comparable_columns)

    query = (
        "SELECT COALESCE(SUM(duplicate_count - 1), 0) "
        "FROM ("
        "SELECT COUNT(*) AS duplicate_count "
        f"FROM {table_ref} "
        f"GROUP BY {group_by_columns} "
        "HAVING COUNT(*) > 1"
        ") AS duplicate_groups"
    )

    return _scalar(source_connector, query)


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

    if vendor == "POSTGRESQL" and base_data_type == "json":
        return f"CAST({column_ref} AS TEXT)"

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


def _scan_sample_values(
    source_connector: Any,
    table_ref: str,
    column_ref: str,
    sample_expression: str,
    limit: int = PATTERN_SCAN_SAMPLE_LIMIT,
) -> list[Any]:
    """Fetch up to `limit` non-null values for in-memory pattern scanning."""
    vendor = _vendor(source_connector)

    if vendor == "SQL_SERVER":
        query = (
            f"SELECT TOP {limit} "
            f"{sample_expression} FROM {table_ref} "
            f"WHERE {column_ref} IS NOT NULL"
        )
    elif vendor == "ORACLE":
        query = (
            f"SELECT {sample_expression} FROM {table_ref} "
            f"WHERE {column_ref} IS NOT NULL "
            f"FETCH FIRST {limit} ROWS ONLY"
        )
    else:
        query = (
            f"SELECT {sample_expression} FROM {table_ref} "
            f"WHERE {column_ref} IS NOT NULL "
            f"LIMIT {limit}"
        )

    cursor = source_connector.connection.cursor()
    try:
        cursor.execute(query)
        rows = cursor.fetchall()
    finally:
        cursor.close()

    return [row[0] for row in rows]


def _sample_values(
    source_connector: Any,
    table_ref: str,
    column_ref: str,
    sample_expression: str,
):
    """Return distinct non-null sample values."""
    vendor = _vendor(source_connector)

    if vendor == "SQL_SERVER":
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

    cursor = source_connector.connection.cursor()
    try:
        cursor.execute(query)
        rows = cursor.fetchall()
    finally:
        cursor.close()

    return [row[0] for row in rows]


def _scalar(source_connector: Any, query: str):
    cursor = source_connector.connection.cursor()
    try:
        cursor.execute(query)
        row = cursor.fetchone()
    finally:
        cursor.close()
    return int(row[0]) if row else 0


def _decimal_scalar(
    source_connector: Any,
    query: str,
) -> float | None:
    """Execute a scalar query and return a rounded decimal value."""
    cursor = source_connector.connection.cursor()

    try:
        cursor.execute(query)
        row = cursor.fetchone()
    finally:
        cursor.close()

    if row is None or row[0] is None:
        return None

    return round(float(row[0]), 4)


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
        escaped = identifier.replace("]", "]]")
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


def mask_sample(value: Any, classification=None) -> str:
    """Format-preserving, fixed-width masking for UI display and LLM classification."""
    del classification
    if value is None:
        return ""

    text = str(value).strip()
    if not text:
        return ""

    # 1. Timestamps & dates -> "2026-**-** **:**" or "2026-**-**"
    ts_match = _ISO_TIMESTAMP_RE.match(text)
    if ts_match:
        return f"{ts_match.group(1)}-**-** **:**"

    date_match = _ISO_DATE_RE.match(text)
    if date_match:
        return f"{date_match.group(1)}-**-**"

    # 2. Email addresses -> "j***@example.com"
    email_match = _EMAIL_RE.match(text)
    if email_match:
        return f"{email_match.group(1)}***@{email_match.group(2)}"

    # 3. Signed/unsigned decimals -> "1***.50" or "-1***.00"
    dec_match = _DECIMAL_RE.match(text)
    if dec_match:
        int_part, frac_part = dec_match.group(1), dec_match.group(2)
        prefix = int_part[:2] if int_part.startswith("-") else int_part[0]
        stars = "**" if len(int_part.lstrip("-")) <= 2 else "***"
        return f"{prefix}{stars}.{frac_part[:2]}"

    # 4. Short 1–2 char values (e.g., ID = 5) -> "5*" instead of bare "*"
    if len(text) <= 2:
        return f"{text[0]}*"

    # 5. Long free-text / multi-word strings (>16 chars) -> fixed 8-char preview "Pen*** 3"
    if len(text) > 16:
        return f"{text[:3]}***{text[-2:]}"

    # 6. Standard words & IDs (3–16 chars) -> fixed 5-char mask "C***t", "7***2"
    return f"{text[0]}***{text[-1]}"