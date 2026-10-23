import asyncio
from src.services.compliance_service import ComplianceService
from src.services.key_vault_service import KeyVaultService
from src.utils.config import get_settings

# Stage 3 mock columns
sample_classified_columns = [
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
        "column_name": "status_flag",
        "display_classification": "PUBLIC",
        "sensitive_data_type": "NONE",
        "is_sensitive": False,
    },
]


async def run_local_evaluation():
    settings = get_settings()
    key_vault = KeyVaultService(settings)

    # db_session=None ensures this runs in-memory without database tables
    service = ComplianceService(settings=settings, key_vault=key_vault, db_session=None)

    print("Evaluating compliance for HIPAA and GDPR...\n")
    results = await service.evaluate_run_compliance(
        discovery_run_id="local_test_run",
        table_name="patients",
        classified_columns=sample_classified_columns,
        selected_frameworks=["HIPAA", "GDPR"],
    )

    for result in results:
        print("=" * 60)
        print(f"FRAMEWORK: {result.framework_code}")
        print(f"Score: {result.metrics.score}% | Risk Band: {result.metrics.risk_band}")
        print(
            f"Counts -> Critical: {result.metrics.critical_count} | "
            f"Serious: {result.metrics.serious_count} | "
            f"Needs Review: {result.metrics.needs_review_count} | "
            f"Total Evaluated: {result.metrics.total_in_scope}"
        )
        print("-" * 60)
        for finding in result.findings:
            print(f"[{finding.status}] Column: {finding.column_name}")
            print(f"  Violation:      {finding.finding}")
            print(f"  Recommendation: {finding.recommendation}\n")


if __name__ == "__main__":
    asyncio.run(run_local_evaluation())