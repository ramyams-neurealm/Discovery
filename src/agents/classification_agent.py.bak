from langchain_core.prompts import ChatPromptTemplate
from src.agents.base import BaseAgent
from src.models.llm_client import build_llm
from src.models.schemas import ClassificationResult
from src.prompts.classification_prompts import CLASSIFICATION_SYSTEM_PROMPT


class DataClassificationAgent(BaseAgent):
    def classify(self, column_payload: dict) -> ClassificationResult:
        llm = build_llm(self.settings, self.key_vault)
        structured_llm = llm.with_structured_output(ClassificationResult)
        prompt = ChatPromptTemplate.from_messages([
            ("system", CLASSIFICATION_SYSTEM_PROMPT),
            ("human", "Classify this column context:\n{payload}"),
        ])
        result = (prompt | structured_llm).invoke({"payload": column_payload})
        if result.confidence < self.settings.classification_confidence_threshold:
            result.needs_human_review = True
            result.review_reason = result.review_reason or "Confidence below threshold"
        return result
