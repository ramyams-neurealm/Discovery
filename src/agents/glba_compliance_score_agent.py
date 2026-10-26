from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel
from src.agents.base import BaseAgent
from src.models.llm_client import build_llm
from src.models.schemas import ClassificationResult, GlbaFinding, GlbaScore
from src.prompts.glba_prompts import GLBA_SYSTEM_PROMPT
from src.tools.glba_control_policy import normalize_glba_finding
from src.tools.scoring_tools import calculate_generic_framework_score


class GlbaFindingBatch(BaseModel):
    findings: list[GlbaFinding]


class GlbaComplianceScoreAgent(BaseAgent):
    def evaluate(self, classifications: list[ClassificationResult]) -> tuple[list[GlbaFinding], GlbaScore]:
        fin_rows = [
            r for r in classifications 
            if r.display_classification.value in ["FINANCIAL", "BANK_ACCOUNT", "PII", "SENSITIVE"]
        ]
        if not fin_rows:
            return [], GlbaScore(overall_score=100, status_band="COMPLIANT")

        llm = build_llm(self.settings, self.key_vault)
        structured_llm = llm.with_structured_output(GlbaFindingBatch)
        prompt = ChatPromptTemplate.from_messages([
            ("system", GLBA_SYSTEM_PROMPT),
            ("human", "Evaluate financial classifications against GLBA Safeguards:\n{payload}"),
        ])
        batch = (prompt | structured_llm).invoke(
            {"payload": [r.model_dump(mode="json") for r in fin_rows]}
        )
        findings = [normalize_glba_finding(f) for f in batch.findings]
        score_val, band = calculate_generic_framework_score(findings)
        return findings, GlbaScore(overall_score=score_val, status_band=band)