# # # Update the imports and DataClassificationAgent in src/agents/classification_agent.py

# # from langchain_core.prompts import ChatPromptTemplate
# # from src.agents.base import BaseAgent
# # from src.models.enums import DisplayClassification
# # from src.models.llm_client import build_llm
# # from src.models.schemas import (
# #     ClassificationResult,
# #     TableClassificationBatchResult,
# # )
# # from src.prompts.classification_prompts import (
# #     CLASSIFICATION_SYSTEM_PROMPT,
# #     TABLE_CLASSIFICATION_SYSTEM_PROMPT,
# # )
# # from src.tools.classification_policy import normalize_classification

# # TABLE_BATCH_CHUNK_SIZE = 30

# # class DataClassificationAgent(BaseAgent):
# #     def classify(self, column_payload: dict) -> ClassificationResult:
# #         # Keep existing classify() method untouched for backward compatibility
# #         llm = build_llm(self.settings, self.key_vault)
# #         structured_llm = llm.with_structured_output(ClassificationResult)
# #         prompt = ChatPromptTemplate.from_messages([
# #             ("system", CLASSIFICATION_SYSTEM_PROMPT),
# #             ("human", "Classify this column context:\n{payload}"),
# #         ])
        
# #         result: ClassificationResult = (prompt | structured_llm).invoke({"payload": column_payload})
# #         result.is_sensitive = result.display_classification.value != "PUBLIC" if hasattr(result.display_classification, "value") else str(result.display_classification).upper() != "PUBLIC"
        
# #         return normalize_classification(
# #             result,
# #             column_payload,
# #             self.settings.classification_confidence_threshold,
# #         )

# #     def classify_table(
# #         self,
# #         schema_name: str,
# #         table_name: str,
# #         object_id: int,
# #         columns: list[dict],
# #     ) -> list[ClassificationResult]:
# #         """Classify all columns of a table in batched LLM invocations."""
# #         if not columns:
# #             return []

# #         llm = build_llm(self.settings, self.key_vault)
# #         structured_llm = llm.with_structured_output(TableClassificationBatchResult)
        
# #         prompt = ChatPromptTemplate.from_messages([
# #             ("system", TABLE_CLASSIFICATION_SYSTEM_PROMPT),
# #             ("human", "Schema: {schema_name}\nTable: {table_name}\nColumns:\n{columns_json}"),
# #         ])

# #         # Slice wide tables into manageable chunks (max 30 columns)
# #         chunks = [
# #             columns[i : i + TABLE_BATCH_CHUNK_SIZE]
# #             for i in range(0, len(columns), TABLE_BATCH_CHUNK_SIZE)
# #         ]

# #         classified_map = {}

# #         for chunk in chunks:
# #             columns_payload = [
# #                 {
# #                     "column_name": col["column_name"],
# #                     "data_type": col.get("data_type"),
# #                     "is_primary_key": col.get("is_primary_key", False),
# #                     "is_foreign_key": col.get("is_foreign_key", False),
# #                     "masked_samples": (col.get("masked_samples") or [])[:3],
# #                     "distinct_count": col.get("distinct_count"),
# #                     "null_percentage": col.get("null_percentage"),
# #                 }
# #                 for col in chunk
# #             ]

# #             batch_response: TableClassificationBatchResult = (prompt | structured_llm).invoke({
# #                 "schema_name": schema_name,
# #                 "table_name": table_name,
# #                 "columns_json": columns_payload,
# #             })

# #             for item in batch_response.classifications:
# #                 classified_map[item.column_name.strip().lower()] = item

# #         # Reconstruct standardized ClassificationResult objects for downstream pipeline
# #         results: list[ClassificationResult] = []
# #         threshold = getattr(self.settings, "classification_confidence_threshold", 0.85)

# #         for col in columns:
# #             col_name = col["column_name"]
# #             classified_item = classified_map.get(col_name.strip().lower())

# #             if classified_item:
# #                 display_cls = classified_item.display_classification
# #                 subtype = classified_item.sensitive_data_type
# #                 conf = classified_item.confidence
# #                 review = classified_item.needs_human_review
# #             else:
# #                 # Defensive fallback if the LLM hallucinated or skipped a column
# #                 display_cls = DisplayClassification.PUBLIC
# #                 subtype = None
# #                 conf = 0.50
# #                 review = True

# #             raw_result = ClassificationResult(
# #                 object_id=object_id,
# #                 schema_name=schema_name,
# #                 table_name=table_name,
# #                 column_name=col_name,
# #                 display_classification=display_cls,
# #                 sensitive_data_type=subtype,
# #                 is_sensitive=(display_cls != DisplayClassification.PUBLIC),
# #                 confidence=conf,
# #                 needs_human_review=review,
# #             )

# #             normalized = normalize_classification(
# #                 result=raw_result,
# #                 payload=col,
# #                 confidence_threshold=threshold,
# #             )
# #             results.append(normalized)

# #         return results










# from langchain_core.prompts import ChatPromptTemplate
# from src.agents.base import BaseAgent
# from src.models.enums import DisplayClassification
# from src.models.llm_client import build_llm
# from src.models.schemas import (
#     ClassificationResult,
#     TableClassificationBatchResult,
# )
# from src.prompts.classification_prompts import (
#     CLASSIFICATION_SYSTEM_PROMPT,
#     TABLE_CLASSIFICATION_SYSTEM_PROMPT,
# )
# from src.tools.classification_policy import normalize_classification

# TABLE_BATCH_CHUNK_SIZE = 30


# class DataClassificationAgent(BaseAgent):
#     def classify(self, column_payload: dict) -> ClassificationResult:
#         # Keep existing classify() method untouched for backward compatibility
#         llm = build_llm(self.settings, self.key_vault)
#         structured_llm = llm.with_structured_output(ClassificationResult)
#         prompt = ChatPromptTemplate.from_messages([
#             ("system", CLASSIFICATION_SYSTEM_PROMPT),
#             ("human", "Classify this column context:\n{payload}"),
#         ])

#         result: ClassificationResult = (prompt | structured_llm).invoke({"payload": column_payload})
#         result.is_sensitive = (
#             result.display_classification.value != "PUBLIC"
#             if hasattr(result.display_classification, "value")
#             else str(result.display_classification).upper() != "PUBLIC"
#         )

#         return normalize_classification(
#             result,
#             column_payload,
#             self.settings.classification_confidence_threshold,
#         )

#     def classify_table(
#         self,
#         schema_name: str,
#         table_name: str,
#         object_id: int,
#         columns: list[dict],
#     ) -> list[ClassificationResult]:
#         """Classify all columns of a table in batched LLM invocations."""
#         if not columns:
#             return []

#         llm = build_llm(self.settings, self.key_vault)
#         structured_llm = llm.with_structured_output(TableClassificationBatchResult)

#         prompt = ChatPromptTemplate.from_messages([
#             ("system", TABLE_CLASSIFICATION_SYSTEM_PROMPT),
#             ("human", "Schema: {schema_name}\nTable: {table_name}\nColumns:\n{columns_json}"),
#         ])

#         # Slice wide tables into manageable chunks (max 30 columns)
#         chunks = [
#             columns[i : i + TABLE_BATCH_CHUNK_SIZE]
#             for i in range(0, len(columns), TABLE_BATCH_CHUNK_SIZE)
#         ]

#         classified_map = {}

#         for chunk in chunks:
#             columns_payload = []
#             for col in chunk:
#                 pattern_hits = (
#                     col.get("pattern_hits")
#                     or col.get("profile_metadata", {}).get("pattern_hits")
#                     or {}
#                 )
#                 entry = {
#                     "column_name": col["column_name"],
#                     "data_type": col.get("data_type"),
#                     "is_primary_key": col.get("is_primary_key", False),
#                     "is_foreign_key": col.get("is_foreign_key", False),
#                     "masked_samples": (col.get("masked_samples") or [])[:3],
#                     "distinct_count": col.get("distinct_count"),
#                     "null_percentage": col.get("null_percentage"),
#                 }
#                 if pattern_hits:
#                     entry["pattern_hits"] = pattern_hits
#                 columns_payload.append(entry)

#             batch_response: TableClassificationBatchResult = (prompt | structured_llm).invoke({
#                 "schema_name": schema_name,
#                 "table_name": table_name,
#                 "columns_json": columns_payload,
#             })

#             for item in batch_response.classifications:
#                 classified_map[item.column_name.strip().lower()] = item

#         # Reconstruct standardized ClassificationResult objects for downstream pipeline
#         results: list[ClassificationResult] = []
#         threshold = getattr(self.settings, "classification_confidence_threshold", 0.85)

#         for col in columns:
#             col_name = col["column_name"]
#             classified_item = classified_map.get(col_name.strip().lower())

#             if classified_item:
#                 display_cls = classified_item.display_classification
#                 subtype = classified_item.sensitive_data_type
#                 conf = classified_item.confidence
#                 review = classified_item.needs_human_review
#             else:
#                 # Defensive fallback if the LLM hallucinated or skipped a column
#                 display_cls = DisplayClassification.PUBLIC
#                 subtype = None
#                 conf = 0.50
#                 review = True

#             raw_result = ClassificationResult(
#                 object_id=object_id,
#                 schema_name=schema_name,
#                 table_name=table_name,
#                 column_name=col_name,
#                 display_classification=display_cls,
#                 sensitive_data_type=subtype,
#                 is_sensitive=(display_cls != DisplayClassification.PUBLIC),
#                 confidence=conf,
#                 needs_human_review=review,
#             )

#             normalized = normalize_classification(
#                 result=raw_result,
#                 payload=col,
#                 confidence_threshold=threshold,
#             )
#             results.append(normalized)

#         return results









import asyncio
from typing import Any

from langchain_core.prompts import ChatPromptTemplate
from src.agents.base import BaseAgent
from src.models.enums import DisplayClassification
from src.models.llm_client import build_llm
from src.models.schemas import (
    ClassificationResult,
    ColumnClassificationItem,
    TableClassificationBatchResult,
)
from src.prompts.classification_prompts import (
    CLASSIFICATION_SYSTEM_PROMPT,
    TABLE_CLASSIFICATION_SYSTEM_PROMPT,
)
from src.tools.classification_policy import normalize_classification

TABLE_BATCH_CHUNK_SIZE = 30
DEFAULT_CLASSIFICATION_CONCURRENCY = 8


class DataClassificationAgent(BaseAgent):
    def classify(self, column_payload: dict) -> ClassificationResult:
        # Keep existing classify() method untouched for backward compatibility
        llm = build_llm(self.settings, self.key_vault)
        structured_llm = llm.with_structured_output(ClassificationResult)
        prompt = ChatPromptTemplate.from_messages([
            ("system", CLASSIFICATION_SYSTEM_PROMPT),
            ("human", "Classify this column context:\n{payload}"),
        ])

        result: ClassificationResult = (prompt | structured_llm).invoke({"payload": column_payload})
        result.is_sensitive = (
            result.display_classification.value != "PUBLIC"
            if hasattr(result.display_classification, "value")
            else str(result.display_classification).upper() != "PUBLIC"
        )

        return normalize_classification(
            result,
            column_payload,
            self.settings.classification_confidence_threshold,
        )

    def _build_chunk_payload(self, chunk: list[dict[str, Any]]) -> list[dict[str, Any]]:
        columns_payload: list[dict[str, Any]] = []
        for col in chunk:
            pattern_hits = (
                col.get("pattern_hits")
                or col.get("profile_metadata", {}).get("pattern_hits")
                or {}
            )
            entry: dict[str, Any] = {
                "column_name": col["column_name"],
                "data_type": col.get("data_type"),
                "is_primary_key": col.get("is_primary_key", False),
                "is_foreign_key": col.get("is_foreign_key", False),
                "masked_samples": (col.get("masked_samples") or [])[:3],
                "distinct_count": col.get("distinct_count"),
                "null_percentage": col.get("null_percentage"),
            }
            if pattern_hits:
                entry["pattern_hits"] = pattern_hits
            columns_payload.append(entry)
        return columns_payload

    def _finalize_table_results(
        self,
        schema_name: str,
        table_name: str,
        object_id: int,
        columns: list[dict[str, Any]],
        classified_map: dict[str, ColumnClassificationItem],
    ) -> list[ClassificationResult]:
        results: list[ClassificationResult] = []
        threshold = getattr(self.settings, "classification_confidence_threshold", 0.85)

        for col in columns:
            col_name = col["column_name"]
            classified_item = classified_map.get(col_name.strip().lower())

            if classified_item:
                display_cls = classified_item.display_classification
                subtype = classified_item.sensitive_data_type
                conf = classified_item.confidence
                review = classified_item.needs_human_review
            else:
                # Defensive fallback if the LLM hallucinated or skipped a column
                display_cls = DisplayClassification.PUBLIC
                subtype = None
                conf = 0.50
                review = True

            raw_result = ClassificationResult(
                object_id=object_id,
                schema_name=schema_name,
                table_name=table_name,
                column_name=col_name,
                display_classification=display_cls,
                sensitive_data_type=subtype,
                is_sensitive=(display_cls != DisplayClassification.PUBLIC),
                confidence=conf,
                needs_human_review=review,
            )

            normalized = normalize_classification(
                result=raw_result,
                payload=col,
                confidence_threshold=threshold,
            )
            results.append(normalized)

        return results

    def classify_table(
        self,
        schema_name: str,
        table_name: str,
        object_id: int,
        columns: list[dict],
    ) -> list[ClassificationResult]:
        """Classify all columns of a table in batched LLM invocations synchronously."""
        if not columns:
            return []

        llm = build_llm(self.settings, self.key_vault)
        structured_llm = llm.with_structured_output(TableClassificationBatchResult)

        prompt = ChatPromptTemplate.from_messages([
            ("system", TABLE_CLASSIFICATION_SYSTEM_PROMPT),
            ("human", "Schema: {schema_name}\nTable: {table_name}\nColumns:\n{columns_json}"),
        ])
        chain = prompt | structured_llm

        chunks = [
            columns[i : i + TABLE_BATCH_CHUNK_SIZE]
            for i in range(0, len(columns), TABLE_BATCH_CHUNK_SIZE)
        ]

        classified_map: dict[str, ColumnClassificationItem] = {}

        for chunk in chunks:
            columns_payload = self._build_chunk_payload(chunk)
            batch_response: TableClassificationBatchResult = chain.invoke({
                "schema_name": schema_name,
                "table_name": table_name,
                "columns_json": columns_payload,
            })

            for item in batch_response.classifications:
                classified_map[item.column_name.strip().lower()] = item

        return self._finalize_table_results(
            schema_name=schema_name,
            table_name=table_name,
            object_id=object_id,
            columns=columns,
            classified_map=classified_map,
        )

    async def classify_table_async(
        self,
        schema_name: str,
        table_name: str,
        object_id: int,
        columns: list[dict],
        semaphore: asyncio.Semaphore | None = None,
    ) -> list[ClassificationResult]:
        """Classify all columns of a table concurrently across 30-column chunks."""
        if not columns:
            return []

        llm = build_llm(self.settings, self.key_vault)
        structured_llm = llm.with_structured_output(TableClassificationBatchResult)

        prompt = ChatPromptTemplate.from_messages([
            ("system", TABLE_CLASSIFICATION_SYSTEM_PROMPT),
            ("human", "Schema: {schema_name}\nTable: {table_name}\nColumns:\n{columns_json}"),
        ])
        chain = prompt | structured_llm

        chunks = [
            columns[i : i + TABLE_BATCH_CHUNK_SIZE]
            for i in range(0, len(columns), TABLE_BATCH_CHUNK_SIZE)
        ]

        async def _classify_chunk(chunk: list[dict[str, Any]]) -> TableClassificationBatchResult:
            payload = {
                "schema_name": schema_name,
                "table_name": table_name,
                "columns_json": self._build_chunk_payload(chunk),
            }
            if semaphore is not None:
                async with semaphore:
                    return await chain.ainvoke(payload)
            return await chain.ainvoke(payload)

        batch_responses = await asyncio.gather(*[_classify_chunk(chunk) for chunk in chunks])

        classified_map: dict[str, ColumnClassificationItem] = {}
        for batch_response in batch_responses:
            for item in batch_response.classifications:
                classified_map[item.column_name.strip().lower()] = item

        return self._finalize_table_results(
            schema_name=schema_name,
            table_name=table_name,
            object_id=object_id,
            columns=columns,
            classified_map=classified_map,
        )

    async def classify_tables_async(
        self,
        tables_map: dict[tuple[str, str, int], list[dict]],
        max_concurrency: int | None = None,
    ) -> list[ClassificationResult]:
        """Classify multiple tables concurrently with bounded LLM concurrency."""
        if not tables_map:
            return []

        concurrency = max_concurrency or getattr(
            self.settings,
            "classification_max_concurrency",
            DEFAULT_CLASSIFICATION_CONCURRENCY,
        )
        semaphore = asyncio.Semaphore(max(1, concurrency))

        tasks = [
            self.classify_table_async(
                schema_name=schema_name,
                table_name=table_name,
                object_id=object_id,
                columns=cols,
                semaphore=semaphore,
            )
            for (schema_name, table_name, object_id), cols in tables_map.items()
        ]

        per_table_results = await asyncio.gather(*tasks)

        results: list[ClassificationResult] = []
        for table_results in per_table_results:
            results.extend(table_results)
        return results