import asyncio
from src.policies.compliance_mapping import filter_columns_for_framework
from src.services.compliance_service import ComplianceService
from src.services.key_vault_service import KeyVaultService
from src.utils.config import get_settings

SAMPLE_INPUT_COLUMNS = [
    {
        "column_name": "pt_ssn",
        "display_classification": "PII",
        "sensitive_data_type": "SOCIAL_SECURITY_NUMBER",
        "is_sensitive": True,
    },
    {
        "column_name": "date_of_birth",
        "display_classification": "PII",
        "sensitive_data_type": "DATE_OF_BIRTH",
        "is_sensitive": True,
    },
    {
        "column_name": "diagnosis_code",
        "display_classification": "PHI",
        "sensitive_data_type": "DIAGNOSIS_CODE",
        "is_sensitive": True,
    },
    {
        "column_name": "card_number",
        "display_classification": "FINANCIAL",
        "sensitive_data_type": "CREDIT_CARD_NUMBER",
        "is_sensitive": True,
    },
    {
        "column_name": "created_at",
        "display_classification": "PUBLIC",
        "sensitive_data_type": "NONE",
        "is_sensitive": False,
    },
]

TARGET_FRAMEWORKS = ["HIPAA", "GDPR", "PCI_DSS"]


async def main():
    print("=" * 70)
    print("STAGE 4 COMPLIANCE ENGINE — END-TO-END LOCAL TEST")
    print("=" * 70)

    # 1. Deterministic Mapping Inspection
    print("\n[PHASE 1] RUNNING DETERMINISTIC STATUTORY MAPPING:")
    print("-" * 70)
    for fw in TARGET_FRAMEWORKS:
        in_scope = filter_columns_for_framework(fw, SAMPLE_INPUT_COLUMNS)
        in_scope_names = [col["column_name"] for col in in_scope]
        print(f"▶ Framework {fw:<8} -> In-Scope: {in_scope_names}")
    print("  • Note: 'created_at' was dropped across all frameworks.")
    print("-" * 70)

    # 2. KeyVault and Service Setup
    print("\n[PHASE 2] INITIALIZING COMPLIANCE ENGINE...")
    settings = get_settings()
    key_vault = KeyVaultService(settings)
    service = ComplianceService(settings=settings, key_vault=key_vault, db_session=None)
    print("  ✓ Settings, KeyVaultService, and ComplianceService ready.")

    # 3. LLM Audit Execution
    print("\n[PHASE 3] EXECUTING LLM COMPLIANCE EVALUATION...")
    results = await service.evaluate_run_compliance(
        discovery_run_id="local_e2e_run_001",
        table_name="patients_and_billing",
        classified_columns=SAMPLE_INPUT_COLUMNS,
        selected_frameworks=TARGET_FRAMEWORKS,
    )

    # 4. Display Summary
    print("\n" + "=" * 70)
    print("FINAL AUDIT RESULTS")
    print("=" * 70)

    for res in results:
        print(f"\n▶ Framework: {res.framework_code}")
        print(f"  Score:     {res.metrics.score}% | Risk Band: {res.metrics.risk_band}")
        print(
            f"  Counts:    In-Scope: {res.metrics.total_in_scope} | "
            f"Critical: {res.metrics.critical_count} | "
            f"Serious: {res.metrics.serious_count} | "
            f"Needs Review: {res.metrics.needs_review_count}"
        )
        print("  Findings:")
        for finding in res.findings:
            print(f"    • [{finding.status}] Column: {finding.column_name}")
            print(f"      Finding: {finding.finding}")
            print(f"      Action:  {finding.recommendation}")

    print("\n" + "=" * 70)
    print("Pipeline completed successfully.")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(main())