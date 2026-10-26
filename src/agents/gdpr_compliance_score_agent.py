from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel
from src.agents.base import BaseAgent
from src.models.llm_client import build_llm
from src.models.schemas import ClassificationResult, GdprFinding, GdprScore
from src.prompts.gdpr_prompts import GDPR_SYSTEM_PROMPT
from src.tools.gdpr_control_policy import normalize_gdpr_finding
from src.tools.scoring_tools import calculate_gdpr_score


class GdprFindingBatch(BaseModel):
    findings: list[GdprFinding]


class GdprComplianceScoreAgent(BaseAgent):
    def evaluate(self, classifications: list[ClassificationResult]) -> tuple[list[GdprFinding], GdprScore]:
        gdpr_rows = [
            row for row in classifications 
            if row.display_classification.value in ["PII", "SENSITIVE", "SPECIAL_CATEGORY", "PHI", "EMAIL", "PASSPORT", "NATIONAL_ID"]
        ]
        
        if not gdpr_rows:
            return [], calculate_gdpr_score([])

        llm = build_llm(self.settings, self.key_vault)
        structured_llm = llm.with_structured_output(GdprFindingBatch)

        prompt = ChatPromptTemplate.from_messages([
            ("system", GDPR_SYSTEM_PROMPT),
            ("human", "Evaluate these personal data classifications against GDPR requirements:\n{payload}"),
        ])

        batch = (prompt | structured_llm).invoke(
            {"payload": [row.model_dump(mode="json") for row in gdpr_rows]}
        )

        findings = [
            normalize_gdpr_finding(finding, getattr(self.settings, "gdpr_confidence_threshold", 0.8))
            for finding in batch.findings
        ]

        return findings, calculate_gdpr_score(findings)