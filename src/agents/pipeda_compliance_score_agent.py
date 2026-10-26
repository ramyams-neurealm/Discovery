from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel
from src.agents.base import BaseAgent
from src.models.llm_client import build_llm
from src.models.schemas import ClassificationResult, PipedaFinding, PipedaScore
from src.prompts.pipeda_prompts import PIPEDA_SYSTEM_PROMPT
from src.tools.pipeda_control_policy import normalize_pipeda_finding
from src.tools.scoring_tools import calculate_generic_framework_score


class PipedaFindingBatch(BaseModel):
    findings: list[PipedaFinding]


class PipedaComplianceScoreAgent(BaseAgent):
    def evaluate(self, classifications: list[ClassificationResult]) -> tuple[list[PipedaFinding], PipedaScore]:
        pipeda_rows = []
        for r in classifications:
            cls_val = r.display_classification.value if hasattr(r.display_classification, "value") else str(r.display_classification)
            if cls_val.upper() in ["PII", "SENSITIVE", "EMPLOYEE", "NATIONAL_ID"]:
                pipeda_rows.append(r)

        if not pipeda_rows:
            return [], PipedaScore(overall_score=100, status_band="COMPLIANT")

        llm = build_llm(self.settings, self.key_vault)
        structured_llm = llm.with_structured_output(PipedaFindingBatch)
        prompt = ChatPromptTemplate.from_messages([
            ("system", PIPEDA_SYSTEM_PROMPT),
            ("human", "Evaluate personal data classifications against PIPEDA Safeguards:\n{payload}"),
        ])
        batch = (prompt | structured_llm).invoke(
            {"payload": [r.model_dump(mode="json") for r in pipeda_rows]}
        )
        findings = [normalize_pipeda_finding(f) for f in batch.findings]
        score_val, band = calculate_generic_framework_score(findings)
        return findings, PipedaScore(overall_score=score_val, status_band=band)