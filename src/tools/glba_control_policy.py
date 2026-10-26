import logging
from typing import Any, Dict, List, Tuple

logger = logging.getLogger(__name__)


def _get_classification_str(item: Any) -> str:
    """Safely extracts classification string from Pydantic model or dict."""
    if isinstance(item, dict):
        val = (
            item.get("display_classification")
            or item.get("classification")
            or item.get("sensitive_data_type")
            or ""
        )
    else:
        val = getattr(
            item,
            "display_classification",
            getattr(
                item,
                "classification",
                getattr(item, "sensitive_data_type", ""),
            ),
        )
    
    if hasattr(val, "value"):
        return str(val.value).upper()
    return str(val).upper()


def normalize_glba_finding(finding: Any) -> Dict[str, Any]:
    """Helper imported by GlbaComplianceScoreAgent to standardize finding dictionaries."""
    if isinstance(finding, dict):
        return {
            "framework": finding.get("framework", "GLBA"),
            "control_id": finding.get("control_id", "GLBA_SAFEGUARDS_314"),
            "object_name": finding.get("object_name", "UNKNOWN_OBJECT"),
            "column_name": finding.get("column_name", "UNKNOWN_COLUMN"),
            "finding_type": finding.get("finding_type", "NPI_DATA_DETECTED"),
            "severity": finding.get("severity", "HIGH"),
            "description": finding.get("description", "GLBA Safeguards rule violation detected.")
        }
    return {
        "framework": getattr(finding, "framework", "GLBA"),
        "control_id": getattr(finding, "control_id", "GLBA_SAFEGUARDS_314"),
        "object_name": getattr(finding, "object_name", "UNKNOWN_OBJECT"),
        "column_name": getattr(finding, "column_name", "UNKNOWN_COLUMN"),
        "finding_type": getattr(finding, "finding_type", "NPI_DATA_DETECTED"),
        "severity": getattr(finding, "severity", "HIGH"),
        "description": getattr(finding, "description", "GLBA Safeguards rule violation detected.")
    }


def build_glba_classification_findings(classifications: List[Any]) -> List[Dict[str, Any]]:
    """Builds GLBA findings without assuming pydantic attribute access."""
    findings = []
    safe_classifications = classifications or []

    for cls in safe_classifications:
        cls_str = _get_classification_str(cls)
        
        if isinstance(cls, dict):
            col_name = cls.get("column_name") or cls.get("field_name") or "UNKNOWN_COLUMN"
            obj_name = cls.get("object_name") or cls.get("table_name") or "UNKNOWN_TABLE"
        else:
            col_name = getattr(cls, "column_name", getattr(cls, "field_name", "UNKNOWN_COLUMN"))
            obj_name = getattr(cls, "object_name", getattr(cls, "table_name", "UNKNOWN_TABLE"))

        if any(keyword in cls_str for keyword in ["FINANCIAL", "NPI", "BANK", "SSN", "TAX", "ACCOUNT"]):
            raw_finding = {
                "framework": "GLBA",
                "control_id": "GLBA_SAFEGUARDS_314",
                "object_name": str(obj_name),
                "column_name": str(col_name),
                "finding_type": "NPI_DATA_DETECTED",
                "severity": "HIGH",
                "description": f"Column '{col_name}' in table '{obj_name}' classified as '{cls_str}' contains Nonpublic Personal Information (NPI)."
            }
            findings.append(normalize_glba_finding(raw_finding))

    return findings


def evaluate_glba_controls(*args, **kwargs) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """
    Safely handles 1-arg, 2-arg, and kwargs calls from discovery_repository.
    ALWAYS returns a 2-tuple: (control_results, summary).
    """
    controls = []
    if len(args) >= 2:
        controls = args[0]
        classifications = args[1]
    elif len(args) == 1:
        classifications = args[0]
    else:
        controls = kwargs.get("controls", [])
        classifications = kwargs.get(
            "classifications",
            kwargs.get("classification_records", []),
        )

    try:
        safe_classifications = list(classifications or [])
        safe_controls = list(controls or [])
        has_financial_data = any(
            any(
                keyword in _get_classification_str(item)
                for keyword in (
                    "FINANCIAL",
                    "NPI",
                    "BANK",
                    "SSN",
                    "TAX",
                    "ACCOUNT",
                )
            )
            for item in safe_classifications
        )

        control_results = []
        for control in safe_controls:
            if isinstance(control, dict):
                get_value = control.get
            else:
                get_value = lambda key, default=None: getattr(
                    control, key, default
                )

            evaluation_type = get_value("evaluation_type", "")
            code = get_value("control_code", "GLBA-UNKNOWN")
            title = get_value("control_title", code)
            if evaluation_type == "FINANCIAL_DATA_DISCOVERY":
                assessment_status = (
                    "PASS" if has_financial_data else "NOT_APPLICABLE"
                )
                explanation = (
                    "Financial data classifications were identified."
                    if has_financial_data
                    else "No financial data classification evidence was found."
                )
                confidence = max(
                    (
                        float(
                            item.get("confidence", 0)
                            if isinstance(item, dict)
                            else getattr(item, "confidence", 0)
                        )
                        for item in safe_classifications
                        if any(
                            keyword in _get_classification_str(item)
                            for keyword in (
                                "FINANCIAL", "NPI", "BANK", "SSN", "TAX", "ACCOUNT"
                            )
                        )
                    ),
                    default=1.0,
                )
                needs_review = False
            elif has_financial_data:
                assessment_status = "INSUFFICIENT_EVIDENCE"
                explanation = (
                    f"Financial data was identified, but {get_value('evidence_type', 'required')} "
                    "evidence was not collected by this discovery run."
                )
                confidence = 1.0
                needs_review = True
            else:
                assessment_status = "NOT_APPLICABLE"
                explanation = "No financial data was identified, so this control was not applied."
                confidence = 1.0
                needs_review = False

            control_results.append(
                {
                    "control_code": code,
                    "control_title": title,
                    "assessment_status": assessment_status,
                    "severity": str(get_value("default_severity", "NEEDS_REVIEW")),
                    "explanation": explanation,
                    "confidence": confidence,
                    "needs_human_review": needs_review,
                }
            )

        applicable_results = [
            result
            for result in control_results
            if result["assessment_status"] != "NOT_APPLICABLE"
        ]
        assessed_results = [
            result
            for result in applicable_results
            if result["assessment_status"] in {"PASS", "PARTIAL", "FAIL"}
        ]
        evidence_coverage = (
            round(100.0 * len(assessed_results) / len(applicable_results), 2)
            if applicable_results
            else 100.0
        )
        score_points = {"PASS": 100.0, "PARTIAL": 50.0, "FAIL": 0.0}
        score = (
            round(
                sum(score_points[row["assessment_status"]] for row in assessed_results)
                / len(assessed_results),
                2,
            )
            if applicable_results and evidence_coverage >= 50 and assessed_results
            else None
        )
        if not applicable_results:
            risk_band = "NOT_APPLICABLE"
        elif score is None:
            risk_band = "INSUFFICIENT_EVIDENCE"
        else:
            risk_band = (
                "GOOD" if score >= 85
                else "NEEDS_REVIEW" if score >= 60
                else "SERIOUS" if score >= 30
                else "CRITICAL"
            )
        summary = {
            "applicable_controls": len(applicable_results),
            "assessed_controls": len(assessed_results),
            "evidence_coverage": evidence_coverage,
            "status_counts": {
                status: sum(
                    result["assessment_status"] == status
                    for result in control_results
                )
                for status in (
                    "PASS", "FAIL", "PARTIAL", "INSUFFICIENT_EVIDENCE",
                    "MANUAL_REVIEW_REQUIRED", "NOT_APPLICABLE", "NOT_ASSESSED",
                )
            },
            "score": score,
            "risk_band": risk_band,
            "policy_version": "glba-control-pack-v1",
        }
    except Exception as exc:
        logger.error(f"Error building GLBA findings: {exc}", exc_info=True)
        control_results = []
        summary = {
            "applicable_controls": 0,
            "assessed_controls": 0,
            "evidence_coverage": 0.0,
            "status_counts": {},
            "score": None,
            "risk_band": "NOT_APPLICABLE",
            "policy_version": "glba-control-pack-v1",
        }

    return control_results, summary