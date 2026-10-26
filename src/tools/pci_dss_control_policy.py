from src.models.schemas import ClassificationResult, PciDssFinding


def _get_classification_str(cls_obj) -> str:
    if isinstance(cls_obj, dict):
        raw = (
            cls_obj.get("display_classification")
            or cls_obj.get("classification")
            or ""
        )
    else:
        raw = getattr(
            cls_obj,
            "display_classification",
            getattr(cls_obj, "classification", ""),
        )

    if hasattr(raw, "value"):
        return str(raw.value).upper()
    return str(raw).upper()


def normalize_pci_dss_finding(finding: PciDssFinding, confidence_threshold: float = 0.8) -> PciDssFinding:
    valid_controls = {"PCI-3.4", "PCI-3.5"}
    if finding.control_code not in valid_controls:
        finding.control_code = "PCI-3.4"
    finding.severity = finding.severity.upper()
    if finding.severity not in {"CRITICAL", "SERIOUS", "WARNING"}:
        finding.severity = "SERIOUS"
    return finding


def build_pci_dss_classification_findings(classifications: list[ClassificationResult]) -> list[PciDssFinding]:
    findings = []
    for cls in classifications:
        val = _get_classification_str(cls)
        if val in ["PCI", "CREDIT_CARD", "FINANCIAL"]:
            if isinstance(cls, dict):
                table_name = cls.get("table_name", "")
                column_name = cls.get("column_name", "")
            else:
                table_name = getattr(cls, "table_name", "")
                column_name = getattr(cls, "column_name", "")
            findings.append(
                PciDssFinding(
                    control_code="PCI-3.4",
                    severity="CRITICAL",
                    table_name=table_name,
                    column_name=column_name,
                    issue_description=f"Unprotected cardholder data identified in column '{column_name}'.",
                    remediation_recommendation="Render Primary Account Number (PAN) unreadable using strong encryption or tokenization."
                )
            )
    return findings


def evaluate_pci_dss_controls(
    *args,
    **kwargs,
) -> tuple[list[dict[str, object]], dict[str, object]]:
    if len(args) >= 2:
        controls = args[0]
        classifications = args[1]
    elif len(args) == 1:
        controls = []
        classifications = args[0]
    else:
        controls = kwargs.get("controls", [])
        classifications = kwargs.get(
            "classifications",
            kwargs.get("classification_records", []),
        )

    safe_classifications = list(classifications or [])
    safe_controls = list(controls or [])

    def value(item, key, default=None):
        if isinstance(item, dict):
            return item.get(key, default)
        return getattr(item, key, default)

    card_classifications = []
    for classification in safe_classifications:
        data_type = str(
            value(classification, "sensitive_data_type", "") or ""
        ).upper()
        classification_name = _get_classification_str(classification)
        if (
            any(token in data_type for token in ("CARD", "PAN", "PAYMENT_CARD"))
            or classification_name in {"PCI", "CREDIT_CARD", "CARDHOLDER_DATA"}
        ):
            card_classifications.append(classification)

    results: list[dict[str, object]] = []
    for control in safe_controls:
        evaluation_type = str(value(control, "evaluation_type", ""))
        card_data_control = evaluation_type == "CARD_DATA_DISCOVERY"
        if card_data_control:
            assessment_status = "PASS" if card_classifications else "NOT_APPLICABLE"
            explanation = (
                f"Identified {len(card_classifications)} card-data column(s)."
                if card_classifications
                else "No cardholder data classification evidence was found."
            )
            confidence = max(
                (float(value(row, "confidence", 0) or 0) for row in card_classifications),
                default=1.0,
            )
            needs_human_review = any(
                bool(value(row, "needs_human_review", False))
                for row in card_classifications
            )
        elif card_classifications:
            assessment_status = "INSUFFICIENT_EVIDENCE"
            explanation = (
                "Cardholder data was identified, but "
                f"{value(control, 'evidence_type', 'required')} evidence "
                "was not collected by this discovery run."
            )
            confidence = 1.0
            needs_human_review = True
        else:
            assessment_status = "NOT_APPLICABLE"
            explanation = (
                "No cardholder data was identified, so this control was not applied."
            )
            confidence = 1.0
            needs_human_review = False

        results.append(
            {
                "control_code": value(control, "control_code", "PCI-UNKNOWN"),
                "control_title": value(control, "control_title", "PCI-DSS control"),
                "assessment_status": assessment_status,
                "severity": value(control, "default_severity", "NEEDS_REVIEW"),
                "explanation": explanation,
                "confidence": confidence,
                "needs_human_review": needs_human_review,
            }
        )

    applicable_count = sum(
        result["assessment_status"] != "NOT_APPLICABLE" for result in results
    )
    assessed_results = [
        result
        for result in results
        if result["assessment_status"] in {"PASS", "PARTIAL", "FAIL"}
    ]
    evidence_coverage = (
        round(100.0 * len(assessed_results) / applicable_count, 2)
        if applicable_count
        else 0.0
    )
    score = None
    if applicable_count and evidence_coverage >= 50 and assessed_results:
        points = {"PASS": 100.0, "PARTIAL": 50.0, "FAIL": 0.0}
        score = round(
            sum(points[result["assessment_status"]] for result in assessed_results)
            / len(assessed_results),
            2,
        )
    if not applicable_count:
        risk_band = "NOT_APPLICABLE"
    elif score is None:
        risk_band = "INSUFFICIENT_EVIDENCE"
    else:
        risk_band = "LOW" if score >= 85 else "MEDIUM" if score >= 50 else "HIGH"

    summary = {
        "card_data_columns_checked": len(card_classifications),
        "applicable_controls": applicable_count,
        "assessed_controls": len(assessed_results),
        "total_controls": len(safe_controls),
        "evidence_coverage": evidence_coverage,
        "score": score,
        "risk_band": risk_band,
    }
    return results, summary