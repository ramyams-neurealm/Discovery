from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel
from src.agents.base import BaseAgent
from src.models.llm_client import build_llm
from src.models.schemas import ClassificationResult, DpdpFinding, DpdpScore
from src.prompts.dpdp_prompts import DPDP_SYSTEM_PROMPT
from src.tools.dpdp_control_policy import normalize_dpdp_finding
from src.tools.scoring_tools import calculate_generic_framework_score


class DpdpFindingBatch(BaseModel):
    findings: list[DpdpFinding]


class DpdpComplianceScoreAgent(BaseAgent):
    def evaluate(self, classifications: list[ClassificationResult]) -> tuple[list[DpdpFinding], DpdpScore]:
        dpdp_rows = []
        for r in classifications:
            cls_val = r.display_classification.value if hasattr(r.display_classification, "value") else str(r.display_classification)
            if cls_val.upper() in ["PII", "SENSITIVE", "EMAIL", "NATIONAL_ID", "PHONE"]:
                dpdp_rows.append(r)

        if not dpdp_rows:
            return [], DpdpScore(overall_score=100, status_band="COMPLIANT")

        llm = build_llm(self.settings, self.key_vault)
        structured_llm = llm.with_structured_output(DpdpFindingBatch)
        prompt = ChatPromptTemplate.from_messages([
            ("system", DPDP_SYSTEM_PROMPT),
            ("human", "Evaluate digital personal data classifications against India DPDP Act:\n{payload}"),
        ])
        batch = (prompt | structured_llm).invoke(
            {"payload": [r.model_dump(mode="json") for r in dpdp_rows]}
        )
        findings = [normalize_dpdp_finding(f) for f in batch.findings]
        score_val, band = calculate_generic_framework_score(findings)
        return findings, DpdpScore(overall_score=score_val, status_band=band)