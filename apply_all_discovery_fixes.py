from __future__ import annotations

import ast
import re
import shutil
from pathlib import Path

ROOT = Path.cwd()


def backup(path: Path) -> None:
    shutil.copy2(path, path.with_suffix(path.suffix + ".bak"))


def write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        backup(path)
    path.write_text(content.rstrip() + "\n", encoding="utf-8")
    ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    print(f"[UPDATED] {path}")


def replace_method(path: Path, name: str, replacement: str) -> None:
    source = path.read_text(encoding="utf-8")
    match = re.search(rf"^    def {re.escape(name)}\(", source, re.MULTILINE)
    if not match:
        raise RuntimeError(f"Method {name} not found in {path}")
    next_method = re.search(r"^    def \w+\(", source[match.end():], re.MULTILINE)
    end = match.end() + next_method.start() if next_method else len(source)
    backup(path)
    path.write_text(source[:match.start()] + replacement.rstrip() + "\n" + source[end:], encoding="utf-8")
    ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    print(f"[PATCHED] {path}: {name}")


def require(paths: list[str]) -> None:
    missing = [p for p in paths if not (ROOT / p).exists()]
    if missing:
        raise RuntimeError(f"Run from repository root. Missing: {missing}")


CLASSIFICATION_POLICY = '''from __future__ import annotations

from typing import Any
from src.models.enums import DisplayClassification

REFERENCE_TABLES = {"diagnosiscodes", "procedurecodes", "pharmacyformularies", "plantypes"}


def _key(value: str) -> str:
    return "".join(ch for ch in value.lower() if ch.isalnum())


def _set(result, display, data_type: str, reason: str) -> None:
    result.display_classification = display
    result.sensitive_data_type = data_type
    result.is_sensitive = display != DisplayClassification.PUBLIC
    result.sensitivity_level = "RESTRICTED" if result.is_sensitive else "PUBLIC"
    result.reason = reason


def normalize_classification(result, payload: dict[str, Any], confidence_threshold: float):
    table = _key(payload["table_name"])
    column = _key(payload["column_name"])

    if column in {"ssn", "socialsecuritynumber"}:
        _set(result, DisplayClassification.PII, "SOCIAL_SECURITY_NUMBER", "Explicit Social Security number field.")
    elif column == "firstname":
        _set(result, DisplayClassification.PII, "FIRST_NAME", "Person first-name field.")
    elif column in {"lastname", "surname"}:
        _set(result, DisplayClassification.PII, "LAST_NAME", "Person last-name field.")
    elif column == "fullname":
        _set(result, DisplayClassification.PII, "FULL_NAME", "Person full-name field.")
    elif column in {"dateofbirth", "dob"}:
        _set(result, DisplayClassification.PII, "DATE_OF_BIRTH", "Person date-of-birth field.")
    elif column == "memberid":
        _set(result, DisplayClassification.PII, "MEMBER_IDENTIFIER", "Member identifier normalized consistently across linked tables.")
    elif column in {"npi", "providerid"}:
        _set(result, DisplayClassification.SENSITIVE, "PROVIDER_IDENTIFIER", "Provider identifier, not patient PHI by itself.")
    elif table in REFERENCE_TABLES and column in {"icdcode", "code", "procedureid", "diagnosisid", "description", "ndccode"}:
        kind = "DIAGNOSIS_CODE" if table == "diagnosiscodes" else "PROCEDURE_CODE"
        _set(result, DisplayClassification.PUBLIC, kind, "Standalone healthcare reference-catalog value, not person-linked PHI by itself.")
    elif column in {"claimid", "claimnumber", "rxclaimid"}:
        _set(result, DisplayClassification.PHI, "CLAIM_IDENTIFIER", "Healthcare claim identifier.")
    elif column in {"dateofservice", "requestdate"} and table in {"claims", "priorauthorizations"}:
        _set(result, DisplayClassification.PHI, "SERVICE_DATE", "Date linked to an identifiable healthcare event.")
    elif column in {"amount", "amountapplied", "billedamount", "paidamount", "totalpaidamount", "totalpremium", "ingredientcost"}:
        _set(result, DisplayClassification.FINANCIAL, "FINANCIAL_AMOUNT", "Monetary amount.")
    elif column == "paymentstatus":
        _set(result, DisplayClassification.FINANCIAL, "PAYMENT_STATUS", "Payment-status field.")

    if result.confidence < confidence_threshold:
        result.needs_human_review = True
        result.review_reason = result.review_reason or "Confidence below threshold."
    return result


def reconcile_linked_identifiers(results, objects):
    by_key = {(r.schema_name, r.table_name, r.column_name): r for r in results}
    for obj in objects:
        for fk in obj.get("foreign_keys", []):
            source = by_key.get((fk["source_schema"], fk["source_table"], fk["source_column"]))
            target = by_key.get((fk["target_schema"], fk["target_table"], fk["target_column"]))
            if not source or not target or source.display_classification == target.display_classification:
                continue
            chosen = source if source.display_classification != DisplayClassification.PUBLIC else target
            changed = target if chosen is source else source
            changed.display_classification = chosen.display_classification
            changed.sensitive_data_type = chosen.sensitive_data_type
            changed.is_sensitive = chosen.is_sensitive
            changed.sensitivity_level = chosen.sensitivity_level
            changed.needs_human_review = True
            changed.review_reason = "Reconciled with a linked PK/FK identifier; human validation required."
    return results


def build_classification_summary(objects, profiles, results):
    discovered = sum(len(obj.get("columns", [])) for obj in objects)
    eligible = len(profiles)
    excluded = max(discovered - eligible, 0)
    return {
        "discovered_columns": discovered,
        "eligible_columns": eligible,
        "classified_columns": len(results),
        "excluded_columns": excluded,
        "exclusion_reasons": {"NO_ELIGIBLE_TABLE_PROFILE": excluded},
    }
'''

HIPAA_POLICY = '''from src.models.enums import HipaaSeverity

REVIEW_SEVERITIES = {HipaaSeverity.NEEDS_REVIEW, HipaaSeverity.SERIOUS, HipaaSeverity.CRITICAL}
NEUTRAL_RECOMMENDATION = (
    "Obtain and review evidence of applicable encryption, masking, access-control, "
    "audit, and retention controls. If evidence confirms a control gap, create and "
    "track an appropriate remediation plan."
)


def normalize_hipaa_finding(finding, confidence_threshold: float):
    finding.verification_status = "PROVISIONAL"
    if finding.severity in REVIEW_SEVERITIES or finding.confidence < confidence_threshold:
        finding.needs_human_review = True
        finding.review_reason = finding.review_reason or (
            "Human review is required because applicable controls could not be "
            "verified from the supplied metadata."
        )
    recommendation = finding.recommendation.lower()
    unsupported = ("implement encryption", "implement and verify", "ensure that", "ensure '", "protect with encryption")
    if any(phrase in recommendation for phrase in unsupported):
        finding.recommendation = NEUTRAL_RECOMMENDATION
    return finding
'''

CLASSIFICATION_AGENT = '''from langchain_core.prompts import ChatPromptTemplate
from src.agents.base import BaseAgent
from src.models.llm_client import build_llm
from src.models.schemas import ClassificationResult
from src.prompts.classification_prompts import CLASSIFICATION_SYSTEM_PROMPT
from src.tools.classification_policy import normalize_classification


class DataClassificationAgent(BaseAgent):
    def classify(self, column_payload: dict) -> ClassificationResult:
        llm = build_llm(self.settings, self.key_vault)
        structured_llm = llm.with_structured_output(ClassificationResult)
        prompt = ChatPromptTemplate.from_messages([
            ("system", CLASSIFICATION_SYSTEM_PROMPT),
            ("human", "Classify this column context:\\n{payload}"),
        ])
        result = (prompt | structured_llm).invoke({"payload": column_payload})
        return normalize_classification(
            result,
            column_payload,
            self.settings.classification_confidence_threshold,
        )
'''

HIPAA_AGENT = '''from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel
from src.agents.base import BaseAgent
from src.models.llm_client import build_llm
from src.models.schemas import ClassificationResult, HipaaFinding, HipaaScore
from src.prompts.hipaa_prompts import HIPAA_SYSTEM_PROMPT
from src.tools.hipaa_policy import normalize_hipaa_finding
from src.tools.scoring_tools import calculate_hipaa_score


class HipaaFindingBatch(BaseModel):
    findings: list[HipaaFinding]


class HipaaComplianceScoreAgent(BaseAgent):
    def evaluate(self, classifications: list[ClassificationResult]) -> tuple[list[HipaaFinding], HipaaScore]:
        phi_rows = [row for row in classifications if row.display_classification.value == "PHI"]
        if not phi_rows:
            return [], calculate_hipaa_score([])
        llm = build_llm(self.settings, self.key_vault)
        structured_llm = llm.with_structured_output(HipaaFindingBatch)
        prompt = ChatPromptTemplate.from_messages([
            ("system", HIPAA_SYSTEM_PROMPT),
            ("human", "Evaluate these PHI classifications:\\n{payload}"),
        ])
        batch = (prompt | structured_llm).invoke({"payload": [row.model_dump(mode="json") for row in phi_rows]})
        findings = [
            normalize_hipaa_finding(finding, self.settings.hipaa_confidence_threshold)
            for finding in batch.findings
        ]
        return findings, calculate_hipaa_score(findings)
'''

CLASSIFICATION_PROMPT = '''CLASSIFICATION_SYSTEM_PROMPT = """
You are the Data Classification Agent for a database discovery platform.
Classify every supplied column as PUBLIC, PII, PHI, FINANCIAL, or SENSITIVE.
Use only supplied metadata and masked evidence. Never invent raw values.
Use stable sensitive_data_type names such as MEMBER_IDENTIFIER, CLAIM_IDENTIFIER,
PROVIDER_IDENTIFIER, DIAGNOSIS_CODE, PROCEDURE_CODE, SERVICE_DATE,
FINANCIAL_AMOUNT, SOCIAL_SECURITY_NUMBER, FIRST_NAME, LAST_NAME, and NONE.
Member identifiers are PII. Claim identifiers linked to healthcare records are PHI.
NPI/provider identifiers identify providers, not patients, and are not PHI solely
because of healthcare context. Standalone diagnosis/procedure reference catalogs
are not person-linked PHI by themselves. Monetary amounts are FINANCIAL.
Mark uncertain or context-dependent results for human review. All results are provisional.
""".strip()
'''

HIPAA_PROMPT = '''HIPAA_SYSTEM_PROMPT = """
You are the HIPAA Compliance and Score Agent. Evaluate only PHI columns.
Return severity, finding, recommendation, confidence, review fields, and
verification_status=PROVISIONAL.
Do not claim encryption, masking, access, audit, or retention controls are absent
without verified evidence. If evidence is unavailable, say the control could not
be verified from supplied metadata. Request evidence review first; recommend
remediation only if a gap is confirmed. GOOD requires positive control evidence.
NEEDS_REVIEW, SERIOUS, and CRITICAL require human review. Never invent controls or raw values.
""".strip()
'''

STATE = '''from typing import Any, TypedDict


class DiscoveryState(TypedDict, total=False):
    discovery_run_id: str
    connection_id: int
    requested_scopes: list[str]
    effective_scopes: list[str]
    source_connection: Any
    objects: list[dict[str, Any]]
    table_profiles: list[dict[str, Any]]
    column_profiles: list[dict[str, Any]]
    classifications: list[Any]
    classification_records: list[dict[str, Any]]
    classification_summary: dict[str, Any]
    dependencies: list[Any]
    dependency_records: list[dict[str, Any]]
    hipaa_findings: list[Any]
    hipaa_finding_records: list[dict[str, Any]]
    hipaa_score: Any
    hipaa_score_id: int
    report: dict[str, Any]
    errors: list[dict[str, Any]]
    status: str
'''

CLASSIFY_METHOD = '''    def _classify(self, state: DiscoveryState) -> DiscoveryState:
        run_id = state["discovery_run_id"]
        if "COLUMN_CLASSIFICATION" not in state["effective_scopes"]:
            return state
        self.repository.update_run_status(run_id, "RUNNING", "COLUMN_CLASSIFICATION", 40)
        self.repository.update_stage(run_id, "COLUMN_CLASSIFICATION", "RUNNING", "Classifying discovered columns")
        profiles = state.get("column_profiles", [])
        try:
            results = []
            keys = (
                "object_id", "column_id", "schema_name", "table_name", "column_name",
                "data_type", "nullable", "is_primary_key", "is_foreign_key",
                "neighboring_columns", "masked_samples", "null_percentage", "distinct_count",
            )
            for profile in profiles:
                results.append(self.classification_agent.classify({key: profile.get(key) for key in keys}))
            results = reconcile_linked_identifiers(results, state.get("objects", []))
            summary = build_classification_summary(state.get("objects", []), profiles, results)
            ids = {(p["schema_name"], p["table_name"], p["column_name"]): p["column_id"] for p in profiles}
            saved = self.repository.save_classifications(run_id, results, ids)
            message = (
                f"Classified {summary['classified_columns']} of {summary['discovered_columns']} "
                f"discovered columns; {summary['excluded_columns']} excluded because "
                "they had no eligible table profile."
            )
            self.repository.update_stage(run_id, "COLUMN_CLASSIFICATION", "COMPLETED", message, len(results), summary["eligible_columns"])
            self.repository.update_run_status(run_id, "RUNNING", "COLUMN_CLASSIFICATION", 60)
            return {**state, "classifications": results, "classification_records": saved, "classification_summary": summary}
        except Exception as error:
            safe = f"Column classification failed: {error.__class__.__name__}"
            self.repository.update_stage(run_id, "COLUMN_CLASSIFICATION", "FAILED", "Column classification failed", error_code="CLASSIFICATION_FAILED", error_message=safe)
            self.repository.update_run_status(run_id, "FAILED", "COLUMN_CLASSIFICATION", 40, "CLASSIFICATION_FAILED", safe)
            raise
'''

CREATE_STAGES_METHOD = '''    def create_run_stages(self, run_id: UUID, effective_scopes: list[str]) -> None:
        effective = set(effective_scopes)
        mapping = {
            "COLUMN_CLASSIFICATION": "COLUMN_CLASSIFICATION",
            "DEPENDENCY_MAPPING": "DEPENDENCY_MAP",
            "HIPAA_COMPLIANCE": "HIPAA_COMPLIANCE",
        }
        query = text("""
            INSERT INTO demooc28.discovery_run_stages
                (discovery_run_id, stage_name, stage_status, message, completed_at)
            VALUES
                (:run_id, :stage_name, :stage_status, :message,
                 CASE WHEN :stage_status = 'SKIPPED' THEN CURRENT_TIMESTAMP ELSE NULL END)
            ON CONFLICT (discovery_run_id, stage_name) DO NOTHING
        """)
        with self.database.connect() as connection:
            for stage in DISCOVERY_STAGES:
                required = mapping.get(stage)
                skipped = bool(required and required not in effective)
                connection.execute(query, {
                    "run_id": str(run_id),
                    "stage_name": stage,
                    "stage_status": "SKIPPED" if skipped else "PENDING",
                    "message": "Stage not requested" if skipped else "Waiting to start",
                })
'''


def main() -> None:
    require([
        "src/orchestration/supervisor.py",
        "src/repositories/discovery_repository.py",
        "src/api/routes.py",
        "src/models/schemas.py",
    ])
    write(ROOT / "src/tools/classification_policy.py", CLASSIFICATION_POLICY)
    write(ROOT / "src/tools/hipaa_policy.py", HIPAA_POLICY)
    write(ROOT / "src/agents/classification_agent.py", CLASSIFICATION_AGENT)
    write(ROOT / "src/agents/hipaa_compliance_score_agent.py", HIPAA_AGENT)
    write(ROOT / "src/prompts/classification_prompts.py", CLASSIFICATION_PROMPT)
    write(ROOT / "src/prompts/hipaa_prompts.py", HIPAA_PROMPT)
    write(ROOT / "src/orchestration/state.py", STATE)

    supervisor = ROOT / "src/orchestration/supervisor.py"
    source = supervisor.read_text(encoding="utf-8")
    import_line = "from src.tools.classification_policy import build_classification_summary, reconcile_linked_identifiers\n"
    if import_line not in source:
        backup(supervisor)
        source = source.replace(
            "from src.repositories.discovery_repository import DiscoveryRepository\n",
            "from src.repositories.discovery_repository import DiscoveryRepository\n" + import_line,
        )
        supervisor.write_text(source, encoding="utf-8")
    replace_method(supervisor, "_classify", CLASSIFY_METHOD)

    repository = ROOT / "src/repositories/discovery_repository.py"
    replace_method(repository, "create_run_stages", CREATE_STAGES_METHOD)
    source = repository.read_text(encoding="utf-8")
    marker = '''        if hasattr(severity, "value"):\n            severity = severity.value\n'''
    guard = marker + '''        if severity in {"NEEDS_REVIEW", "SERIOUS", "CRITICAL"}:\n            payload["needs_human_review"] = True\n            payload["review_reason"] = payload.get("review_reason") or "Human review is required because applicable controls could not be verified from the supplied metadata."\n        payload["verification_status"] = "PROVISIONAL"\n'''
    if marker in source and "applicable controls could not be verified" not in source:
        backup(repository)
        repository.write_text(source.replace(marker, guard, 1), encoding="utf-8")

    routes = ROOT / "src/api/routes.py"
    source = routes.read_text(encoding="utf-8")
    cleaned = source.replace('        record.pop("password_plaintext", None)\n', '')
    cleaned = cleaned.replace('    record.pop("password_plaintext", None)\n', '')
    cleaned = cleaned.replace('    updated_record.pop("password_plaintext", None)\n', '')
    if cleaned != source:
        backup(routes)
        routes.write_text(cleaned, encoding="utf-8")

    for path in [supervisor, repository, routes]:
        ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    print("[OK] All fixes applied and syntax validated.")
    print("Now run: python -m compileall -f src")
    print("Then run: python -m pytest -v")


if __name__ == "__main__":
    main()
