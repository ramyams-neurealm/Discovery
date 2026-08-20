from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel
from src.agents.base import BaseAgent
from src.models.llm_client import build_llm
from src.models.schemas import ClassificationResult, HipaaFinding, HipaaScore
from src.prompts.hipaa_prompts import HIPAA_SYSTEM_PROMPT
from src.tools.scoring_tools import calculate_hipaa_score


class HipaaFindingBatch(BaseModel):
    findings: list[HipaaFinding]


class HipaaComplianceScoreAgent(BaseAgent):
    def evaluate(self, classifications: list[ClassificationResult]) -> tuple[list[HipaaFinding], HipaaScore]:
        phi_rows = [r for r in classifications if r.display_classification.value == "PHI"]
        if not phi_rows:
            return [], calculate_hipaa_score([])
        llm = build_llm(self.settings, self.key_vault)
        structured_llm = llm.with_structured_output(HipaaFindingBatch)
        prompt = ChatPromptTemplate.from_messages([
            ("system", HIPAA_SYSTEM_PROMPT),
            ("human", "Evaluate these PHI classifications:\n{payload}"),
        ])
        batch = (prompt | structured_llm).invoke({"payload": [r.model_dump() for r in phi_rows]})
        for finding in batch.findings:
            if finding.confidence < self.settings.hipaa_confidence_threshold:
                finding.needs_human_review = True
                finding.review_reason = finding.review_reason or "Confidence below threshold"
        return batch.findings, calculate_hipaa_score(batch.findings)
