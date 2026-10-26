from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel
from src.agents.base import BaseAgent
from src.models.llm_client import build_llm
from src.models.schemas import ClassificationResult, CcpaFinding, CcpaScore
from src.prompts.ccpa_prompts import CCPA_SYSTEM_PROMPT
from src.tools.ccpa_control_policy import normalize_ccpa_finding
from src.tools.scoring_tools import calculate_generic_framework_score


class CcpaFindingBatch(BaseModel):
    findings: list[CcpaFinding]


class CcpaComplianceScoreAgent(BaseAgent):
    def evaluate(self, classifications: list[ClassificationResult]) -> tuple[list[CcpaFinding], CcpaScore]:
        ccpa_rows = []
        for r in classifications:
            cls_val = r.display_classification.value if hasattr(r.display_classification, "value") else str(r.display_classification)
            if cls_val.upper() in ["PII", "SENSITIVE", "LOCATION", "PASSWORD", "BIOMETRIC"]:
                ccpa_rows.append(r)

        if not ccpa_rows:
            return [], CcpaScore(overall_score=100, status_band="COMPLIANT")

        llm = build_llm(self.settings, self.key_vault)
        structured_llm = llm.with_structured_output(CcpaFindingBatch)
        prompt = ChatPromptTemplate.from_messages([
            ("system", CCPA_SYSTEM_PROMPT),
            ("human", "Evaluate personal data classifications against CCPA/CPRA requirements:\n{payload}"),
        ])
        batch = (prompt | structured_llm).invoke(
            {"payload": [r.model_dump(mode="json") for r in ccpa_rows]}
        )
        findings = [normalize_ccpa_finding(f) for f in batch.findings]
        score_val, band = calculate_generic_framework_score(findings)
        return findings, CcpaScore(overall_score=score_val, status_band=band)