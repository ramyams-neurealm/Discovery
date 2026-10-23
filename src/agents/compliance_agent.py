import asyncio
from typing import Any
from langchain_core.prompts import ChatPromptTemplate
from src.agents.base import BaseAgent
from src.models.llm_client import build_llm
from src.models.compliance_schemas import FrameworkBatchOutput
from src.prompts.compliance_prompts import FRAMEWORK_PROMPTS


class ComplianceAgent(BaseAgent):
    """Evaluates in-scope columns against statutory framework requirements."""

    def evaluate_framework(
        self,
        framework_code: str,
        table_name: str,
        columns: list[dict[str, Any]],
    ) -> FrameworkBatchOutput:
        """Evaluates columns for a single framework synchronously."""
        fw = framework_code.upper()
        system_prompt = FRAMEWORK_PROMPTS.get(
            fw,
            f"You are a regulatory compliance auditor for {fw}. Evaluate the columns and provide findings.",
        )

        llm = build_llm(self.settings, self.key_vault)
        structured_llm = llm.with_structured_output(FrameworkBatchOutput)

        prompt = ChatPromptTemplate.from_messages([
            ("system", system_prompt),
            (
                "human",
                "Evaluate the following in-scope columns for framework {framework_code} in table '{table_name}':\n"
                "{columns_payload}\n"
                "Return status, finding, and recommendation for each column."
            ),
        ])

        # payload = [
        #     {
        #         "column_name": col.get("column_name"),
        #         "display_classification": col.get("display_classification"),
        #         "sensitive_data_type": col.get("sensitive_data_type"),
        #     }
        #     for col in columns
        # ]
        payload = [
            {
                "column_name": col.get("column_name"),
                "display_classification": getattr(col.get("display_classification"), "value", str(col.get("display_classification"))).split(".")[-1],
                "sensitive_data_type": getattr(col.get("sensitive_data_type"), "value", str(col.get("sensitive_data_type"))).split(".")[-1],
            }
            for col in columns
        ]

        result = (prompt | structured_llm).invoke({
            "framework_code": fw,
            "table_name": table_name,
            "columns_payload": payload,
        })
        return result

    async def evaluate_framework_async(
        self,
        framework_code: str,
        table_name: str,
        columns: list[dict[str, Any]],
    ) -> FrameworkBatchOutput:
        """Asynchronously runs the evaluation to allow concurrent execution."""
        return await asyncio.to_thread(
            self.evaluate_framework, framework_code, table_name, columns
        )