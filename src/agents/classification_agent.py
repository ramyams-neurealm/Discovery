# Update the imports and DataClassificationAgent in src/agents/classification_agent.py

from langchain_core.prompts import ChatPromptTemplate
from src.agents.base import BaseAgent
from src.models.enums import DisplayClassification
from src.models.llm_client import build_llm
from src.models.schemas import (
    ClassificationResult,
    TableClassificationBatchResult,
)
from src.prompts.classification_prompts import (
    CLASSIFICATION_SYSTEM_PROMPT,
    TABLE_CLASSIFICATION_SYSTEM_PROMPT,
)
from src.tools.classification_policy import normalize_classification

TABLE_BATCH_CHUNK_SIZE = 30

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
        result.is_sensitive = result.display_classification.value != "PUBLIC" if hasattr(result.display_classification, "value") else str(result.display_classification).upper() != "PUBLIC"
        
        return normalize_classification(
            result,
            column_payload,
            self.settings.classification_confidence_threshold,
        )

    def classify_table(
        self,
        schema_name: str,
        table_name: str,
        object_id: int,
        columns: list[dict],
    ) -> list[ClassificationResult]:
        """Classify all columns of a table in batched LLM invocations."""
        if not columns:
            return []

        llm = build_llm(self.settings, self.key_vault)
        structured_llm = llm.with_structured_output(TableClassificationBatchResult)
        
        prompt = ChatPromptTemplate.from_messages([
            ("system", TABLE_CLASSIFICATION_SYSTEM_PROMPT),
            ("human", "Schema: {schema_name}\nTable: {table_name}\nColumns:\n{columns_json}"),
        ])

        # Slice wide tables into manageable chunks (max 30 columns)
        chunks = [
            columns[i : i + TABLE_BATCH_CHUNK_SIZE]
            for i in range(0, len(columns), TABLE_BATCH_CHUNK_SIZE)
        ]

        classified_map = {}

        for chunk in chunks:
            columns_payload = [
                {
                    "column_name": col["column_name"],
                    "data_type": col.get("data_type"),
                    "is_primary_key": col.get("is_primary_key", False),
                    "is_foreign_key": col.get("is_foreign_key", False),
                    "masked_samples": (col.get("masked_samples") or [])[:3],
                    "distinct_count": col.get("distinct_count"),
                    "null_percentage": col.get("null_percentage"),
                }
                for col in chunk
            ]

            batch_response: TableClassificationBatchResult = (prompt | structured_llm).invoke({
                "schema_name": schema_name,
                "table_name": table_name,
                "columns_json": columns_payload,
            })

            for item in batch_response.classifications:
                classified_map[item.column_name.strip().lower()] = item

        # Reconstruct standardized ClassificationResult objects for downstream pipeline
        results: list[ClassificationResult] = []
        threshold = getattr(self.settings, "classification_confidence_threshold", 0.85)

        for col in columns:
            col_name = col["column_name"]
            classified_item = classified_map.get(col_name.strip().lower())

            if classified_item:
                display_cls = classified_item.display_classification
                conf = classified_item.confidence
                review = classified_item.needs_human_review
            else:
                # Defensive fallback if the LLM hallucinated or skipped a column
                display_cls = DisplayClassification.PUBLIC
                conf = 0.50
                review = True

            raw_result = ClassificationResult(
                object_id=object_id,
                schema_name=schema_name,
                table_name=table_name,
                column_name=col_name,
                display_classification=display_cls,
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