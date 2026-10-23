import asyncio
from typing import Any
from src.agents.compliance_agent import ComplianceAgent
from src.models.compliance_schemas import (
    FrameworkAssessmentResult,
    FrameworkMetrics,
    RiskBand,
)
from src.policies.compliance_mapping import filter_columns_for_framework


def calculate_metrics(evaluations: list[Any]) -> FrameworkMetrics:
    """Calculates penalty deductions and assigns the risk band."""
    n = len(evaluations)
    if n == 0:
        return FrameworkMetrics(
            score=100,
            risk_band=RiskBand.GOOD,
            total_in_scope=0,
            critical_count=0,
            serious_count=0,
            needs_review_count=0,
        )

    critical_count = sum(1 for e in evaluations if e.status == "Critical")
    serious_count = sum(1 for e in evaluations if e.status == "Serious")
    review_count = sum(1 for e in evaluations if e.status == "Needs review")

    total_penalty = (critical_count * 25) + (serious_count * 15) + (review_count * 5)
    raw_score = 100.0 - (total_penalty / n)
    score = max(0, min(100, round(raw_score)))

    if score >= 85:
        risk_band = RiskBand.GOOD
    elif score >= 60:
        risk_band = RiskBand.MODERATE_RISK
    elif score >= 30:
        risk_band = RiskBand.SERIOUS_RISK
    else:
        risk_band = RiskBand.CRITICAL_RISK

    return FrameworkMetrics(
        score=score,
        risk_band=risk_band,
        total_in_scope=n,
        critical_count=critical_count,
        serious_count=serious_count,
        needs_review_count=review_count,
    )


class ComplianceService:
    def __init__(self, settings: Any, key_vault: Any, db_session: Any = None):
        self.settings = settings
        self.key_vault = key_vault
        self.db = db_session
        self.agent = ComplianceAgent(settings=settings, key_vault=key_vault)

    async def evaluate_run_compliance(
        self,
        discovery_run_id: str,
        table_name: str,
        classified_columns: list[dict[str, Any]],
        selected_frameworks: list[str],
    ) -> list[FrameworkAssessmentResult]:
        """
        Filters in-scope columns, fires parallel agents for selected frameworks,
        and aggregates findings.
        """
        # Step 1: Prepare concurrent tasks only for requested frameworks
        tasks = []
        framework_order: list[str] = []

        for fw in selected_frameworks:
            fw_code = fw.upper().strip()
            in_scope_cols = filter_columns_for_framework(fw_code, classified_columns)
            
            # If no sensitive columns are in scope for this framework, skip LLM calls
            if not in_scope_cols:
                continue

            tasks.append(
                self.agent.evaluate_framework_async(fw_code, table_name, in_scope_cols)
            )
            framework_order.append(fw_code)

        if not tasks:
            return []

        # Step 2: Execute all requested framework evaluations concurrently
        batch_results = await asyncio.gather(*tasks, return_exceptions=True)

        # Step 3: Compute scores and structure response
        completed_results: list[FrameworkAssessmentResult] = []
        for fw_code, batch_output in zip(framework_order, batch_results):
            # if isinstance(batch_output, Exception):
            #     # Log error and continue with other frameworks
            #     continue
            # for fw_code, batch_output in zip(framework_order, batch_results):
            if isinstance(batch_output, Exception):
                print(f"\n[ERROR] Evaluation failed for framework '{fw_code}':")
                import traceback
                traceback.print_exception(type(batch_output), batch_output, batch_output.__traceback__)
                continue

            findings = batch_output.evaluations
            metrics = calculate_metrics(findings)

            result = FrameworkAssessmentResult(
                framework_code=fw_code,
                metrics=metrics,
                findings=findings,
            )
            completed_results.append(result)

            # Step 4: Persist to PostgreSQL if DB session is available
            if self.db:
                self._persist_assessment(discovery_run_id, table_name, result)

        return completed_results

    def _persist_assessment(
        self,
        discovery_run_id: str,
        table_name: str,
        result: FrameworkAssessmentResult,
    ) -> None:
        """Stores findings and score cards in demooc28 tables."""
        # INSERT / ON CONFLICT UPDATE into demooc28.compliance_assessments
        # INSERT into demooc28.compliance_findings
        pass