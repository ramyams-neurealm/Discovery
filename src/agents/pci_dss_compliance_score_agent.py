from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel
from src.agents.base import BaseAgent
from src.models.llm_client import build_llm
from src.models.schemas import ClassificationResult, PciDssFinding, PciDssScore
from src.prompts.pci_dss_prompts import PCI_DSS_SYSTEM_PROMPT
from src.tools.pci_dss_control_policy import normalize_pci_dss_finding
from src.tools.scoring_tools import calculate_generic_framework_score


class PciFindingBatch(BaseModel):
    findings: list[PciDssFinding]


class PciDssComplianceScoreAgent(BaseAgent):
    def evaluate(self, classifications: list[ClassificationResult]) -> tuple[list[PciDssFinding], PciDssScore]:
        card_rows = []
        for r in classifications:
            cls_val = r.display_classification.value if hasattr(r.display_classification, "value") else str(r.display_classification)
            if cls_val.upper() in ["PCI", "CREDIT_CARD", "FINANCIAL", "SENSITIVE"]:
                card_rows.append(r)

        if not card_rows:
            return [], PciDssScore(overall_score=100, status_band="COMPLIANT")

        llm = build_llm(self.settings, self.key_vault)
        structured_llm = llm.with_structured_output(PciFindingBatch)
        prompt = ChatPromptTemplate.from_messages([
            ("system", PCI_DSS_SYSTEM_PROMPT),
            ("human", "Evaluate cardholder data classifications against PCI-DSS:\n{payload}"),
        ])
        batch = (prompt | structured_llm).invoke(
            {"payload": [r.model_dump(mode="json") for r in card_rows]}
        )
        findings = [normalize_pci_dss_finding(f) for f in batch.findings]
        score_val, band = calculate_generic_framework_score(findings)
        return findings, PciDssScore(overall_score=score_val, status_band=band)