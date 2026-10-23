# # from __future__ import annotations

# # from typing import Any
# # from sqlalchemy import text
# # from src.services.database import MetadataDatabase


# # class ComplianceRepository:
# #     def __init__(self, database: MetadataDatabase):
# #         self.database = database

# #     def save_framework_assessment(
# #         self,
# #         discovery_run_id: str,
# #         table_name: str,
# #         framework_result: Any,
# #     ) -> int:
# #         """
# #         Persists assessment summary and individual column findings
# #         into demooc28.compliance_assessments and demooc28.compliance_findings.
# #         """
# #         metrics = framework_result.metrics

# #         with self.database.transaction() as session:
# #             # 1. Insert or update the framework assessment header
# #             assessment_stmt = text("""
# #                 INSERT INTO demooc28.compliance_assessments (
# #                     discovery_run_id,
# #                     framework_code,
# #                     compliance_score,
# #                     risk_band,
# #                     in_scope_count,
# #                     critical_count,
# #                     serious_count,
# #                     needs_review_count
# #                 ) VALUES (
# #                     :run_id,
# #                     :framework_code,
# #                     :score,
# #                     :risk_band,
# #                     :in_scope_count,
# #                     :critical_count,
# #                     :serious_count,
# #                     :needs_review_count
# #                 )
# #                 ON CONFLICT (discovery_run_id, framework_code) 
# #                 DO UPDATE SET
# #                     compliance_score = EXCLUDED.compliance_score,
# #                     risk_band = EXCLUDED.risk_band,
# #                     in_scope_count = EXCLUDED.in_scope_count,
# #                     critical_count = EXCLUDED.critical_count,
# #                     serious_count = EXCLUDED.serious_count,
# #                     needs_review_count = EXCLUDED.needs_review_count,
# #                     created_at = NOW()
# #                 RETURNING assessment_id;
# #             """)

# #             result = session.execute(
# #                 assessment_stmt,
# #                 {
# #                     "run_id": str(discovery_run_id),
# #                     "framework_code": framework_result.framework_code,
# #                     "score": int(round(metrics.score)),
# #                     "risk_band": str(metrics.risk_band),
# #                     "in_scope_count": metrics.total_in_scope,
# #                     "critical_count": metrics.critical_count,
# #                     "serious_count": metrics.serious_count,
# #                     "needs_review_count": metrics.needs_review_count,
# #                 },
# #             )
# #             assessment_id = result.scalar_one()

# #             # 2. Clear old findings for this assessment before re-inserting
# #             session.execute(
# #                 text("DELETE FROM demooc28.compliance_findings WHERE assessment_id = :assessment_id;"),
# #                 {"assessment_id": assessment_id},
# #             )

# #             # 3. Insert each column finding
# #             finding_stmt = text("""
# #                 INSERT INTO demooc28.compliance_findings (
# #                     assessment_id,
# #                     table_name,
# #                     column_name,
# #                     status,
# #                     finding_text,
# #                     recommendation_text,
# #                     is_remediated
# #                 ) VALUES (
# #                     :assessment_id,
# #                     :table_name,
# #                     :column_name,
# #                     :status,
# #                     :finding_text,
# #                     :recommendation_text,
# #                     FALSE
# #                 );
# #             """)

# #             for finding in framework_result.findings:
# #                 session.execute(
# #                     finding_stmt,
# #                     {
# #                         "assessment_id": assessment_id,
# #                         "table_name": table_name,
# #                         "column_name": finding.column_name,
# #                         "status": str(finding.status),
# #                         "finding_text": finding.finding,
# #                         "recommendation_text": finding.recommendation,
# #                     },
# #                 )

# #             return assessment_id

# from __future__ import annotations

# from typing import Any
# from uuid import UUID
# from sqlalchemy import text
# from src.services.database import MetadataDatabase


# class ComplianceRepository:
#     def __init__(self, database: MetadataDatabase):
#         self.database = database

#     def save_framework_assessment(
#         self,
#         discovery_run_id: str | UUID,
#         framework_code: str,
#         metrics: Any,
#         findings: list[Any],
#     ) -> int:
#         """
#         Persists run-level assessment score and all individual column findings
#         across tables into demooc28.compliance_assessments and demooc28.compliance_findings.
#         """
#         run_id_str = str(discovery_run_id)
#         fw_code = framework_code.upper().strip()

#         with self.database.transaction() as session:
#             # 1. Upsert framework assessment header and score
#             assessment_stmt = text("""
#                 INSERT INTO demooc28.compliance_assessments (
#                     discovery_run_id,
#                     framework_code,
#                     compliance_score,
#                     risk_band,
#                     in_scope_count,
#                     critical_count,
#                     serious_count,
#                     needs_review_count
#                 ) VALUES (
#                     :run_id,
#                     :framework_code,
#                     :score,
#                     :risk_band,
#                     :in_scope_count,
#                     :critical_count,
#                     :serious_count,
#                     :needs_review_count
#                 )
#                 ON CONFLICT (discovery_run_id, framework_code) 
#                 DO UPDATE SET
#                     compliance_score = EXCLUDED.compliance_score,
#                     risk_band = EXCLUDED.risk_band,
#                     in_scope_count = EXCLUDED.in_scope_count,
#                     critical_count = EXCLUDED.critical_count,
#                     serious_count = EXCLUDED.serious_count,
#                     needs_review_count = EXCLUDED.needs_review_count,
#                     created_at = NOW()
#                 RETURNING assessment_id;
#             """)

#             result = session.execute(
#                 assessment_stmt,
#                 {
#                     "run_id": run_id_str,
#                     "framework_code": fw_code,
#                     "score": int(round(metrics.score)),
#                     "risk_band": str(getattr(metrics.risk_band, "value", metrics.risk_band)),
#                     "in_scope_count": metrics.total_in_scope,
#                     "critical_count": metrics.critical_count,
#                     "serious_count": metrics.serious_count,
#                     "needs_review_count": metrics.needs_review_count,
#                 },
#             )
#             assessment_id = result.scalar_one()

#             # 2. Clear previous findings for this assessment before re-inserting
#             session.execute(
#                 text("DELETE FROM demooc28.compliance_findings WHERE assessment_id = :assessment_id;"),
#                 {"assessment_id": assessment_id},
#             )

#             # 3. Insert findings across all evaluated tables
#             # finding_stmt = text("""
#             #     INSERT INTO demooc28.compliance_findings (
#             #         assessment_id,
#             #         table_name,
#             #         column_name,
#             #         status,
#             #         finding_text,
#             #         recommendation_text,
#             #         is_remediated
#             #     ) VALUES (
#             #         :assessment_id,
#             #         :table_name,
#             #         :column_name,
#             #         :status,
#             #         :finding_text,
#             #         :recommendation_text,
#             #         FALSE
#             #     );
#             # """)

#             # for finding in findings:
#             #     table_name = getattr(finding, "table_name", "unknown_table")
#             #     session.execute(
#             #         finding_stmt,
#             #         {
#             #             "assessment_id": assessment_id,
#             #             "table_name": table_name,
#             #             "column_name": finding.column_name,
#             #             "status": str(finding.status),
#             #             "finding_text": finding.finding,
#             #             "recommendation_text": finding.recommendation,
#             #         },
#             #     )
#             finding_stmt = text("""
#                 INSERT INTO demooc28.compliance_findings (
#                     assessment_id,
#                     table_name,
#                     column_name,
#                     status,
#                     finding_text,
#                     recommendation_text,
#                     needs_human_review,
#                     is_remediated
#                 ) VALUES (
#                     :assessment_id,
#                     :table_name,
#                     :column_name,
#                     :status,
#                     :finding_text,
#                     :recommendation_text,
#                     :needs_human_review,
#                     FALSE
#                 );
#             """)

#             for finding in findings:
#                 table_name = getattr(finding, "table_name", "unknown_table")
#                 session.execute(
#                     finding_stmt,
#                     {
#                         "assessment_id": assessment_id,
#                         "table_name": table_name,
#                         "column_name": finding.column_name,
#                         "status": str(finding.status),
#                         "finding_text": finding.finding,
#                         "recommendation_text": finding.recommendation,
#                         "needs_human_review": str(finding.status).upper() == "NEEDS REVIEW",
#                     },
#                 )
#             return assessment_id

#     def get_compliance_results(
#         self,
#         discovery_run_id: str | UUID,
#     ) -> list[dict[str, Any]]:
#         """
#         Retrieves consolidated compliance assessments and their column findings
#         for a given discovery run.
#         """
#         run_id_str = str(discovery_run_id)

#         assessments_query = text("""
#             SELECT 
#                 assessment_id,
#                 discovery_run_id,
#                 framework_code,
#                 compliance_score,
#                 risk_band,
#                 in_scope_count,
#                 critical_count,
#                 serious_count,
#                 needs_review_count,
#                 created_at
#             FROM demooc28.compliance_assessments
#             WHERE discovery_run_id = :run_id
#             ORDER BY framework_code;
#         """)

#         findings_query = text("""
#             SELECT 
#                 finding_id,
#                 assessment_id,
#                 table_name,
#                 column_name,
#                 status,
#                 finding_text,
#                 recommendation_text,
#                 is_remediated,
#                 created_at
#             FROM demooc28.compliance_findings
#             WHERE assessment_id = :assessment_id
#             ORDER BY 
#                 CASE status 
#                     WHEN 'Critical' THEN 1 
#                     WHEN 'Serious' THEN 2 
#                     ELSE 3 
#                 END,
#                 table_name, 
#                 column_name;
#         """)

#         results: list[dict[str, Any]] = []

#         with self.database.connect() as connection:
#             assessment_rows = connection.execute(
#                 assessments_query,
#                 {"run_id": run_id_str},
#             ).mappings().all()

#             for a_row in assessment_rows:
#                 assessment_data = dict(a_row)
#                 assessment_id = assessment_data["assessment_id"]

#                 finding_rows = connection.execute(
#                     findings_query,
#                     {"assessment_id": assessment_id},
#                 ).mappings().all()

#                 assessment_data["findings"] = [dict(f) for f in finding_rows]
#                 results.append(assessment_data)

#         return results

from __future__ import annotations

from typing import Any
from uuid import UUID
from sqlalchemy import text
from src.services.database import MetadataDatabase


class ComplianceRepository:
    def __init__(self, database: MetadataDatabase):
        self.database = database

    def save_framework_assessment(
        self,
        discovery_run_id: str | UUID,
        framework_code: str,
        metrics: Any,
        findings: list[Any],
    ) -> int:
        """
        Persists run-level assessment score and all individual column findings
        across tables into demooc28.compliance_assessments and demooc28.compliance_findings.
        """
        run_id_str = str(discovery_run_id)
        fw_code = framework_code.upper().strip()

        # MetadataDatabase uses .connect() context manager across this project
        with self.database.connect() as connection:
            # 1. Upsert framework assessment header and score
            # assessment_stmt = text("""
            #     INSERT INTO demooc28.compliance_assessments (
            #         discovery_run_id,
            #         framework_code,
            #         compliance_score,
            #         risk_band,
            #         in_scope_count,
            #         critical_count,
            #         serious_count,
            #         needs_review_count
            #     ) VALUES (
            #         :run_id,
            #         :framework_code,
            #         :score,
            #         :risk_band,
            #         :in_scope_count,
            #         :critical_count,
            #         :serious_count,
            #         :needs_review_count
            #     )
            #     ON CONFLICT (discovery_run_id, framework_code) 
            #     DO UPDATE SET
            #         compliance_score = EXCLUDED.compliance_score,
            #         risk_band = EXCLUDED.risk_band,
            #         in_scope_count = EXCLUDED.in_scope_count,
            #         critical_count = EXCLUDED.critical_count,
            #         serious_count = EXCLUDED.serious_count,
            #         needs_review_count = EXCLUDED.needs_review_count,
            #         created_at = NOW()
            #     RETURNING assessment_id;
            # """)
            # 1. Inside save_framework_assessment:
            assessment_stmt = text("""
                INSERT INTO demooc28.compliance_assessments (
                    discovery_run_id,
                    framework_code,
                    compliance_score,
                    risk_band,
                    in_scope_count,
                    critical_count,
                    serious_count,
                    needs_review_count
                ) VALUES (
                    CAST(:run_id AS UUID),
                    :framework_code,
                    :score,
                    :risk_band,
                    :in_scope_count,
                    :critical_count,
                    :serious_count,
                    :needs_review_count
                )
                ON CONFLICT (discovery_run_id, framework_code) 
                DO UPDATE SET
                    compliance_score = EXCLUDED.compliance_score,
                    risk_band = EXCLUDED.risk_band,
                    in_scope_count = EXCLUDED.in_scope_count,
                    critical_count = EXCLUDED.critical_count,
                    serious_count = EXCLUDED.serious_count,
                    needs_review_count = EXCLUDED.needs_review_count,
                    created_at = NOW()
                RETURNING assessment_id;
            """)
            result = connection.execute(
                assessment_stmt,
                {
                    "run_id": run_id_str,
                    "framework_code": fw_code,
                    "score": int(round(metrics.score)),
                    "risk_band": str(getattr(metrics.risk_band, "value", metrics.risk_band)),
                    "in_scope_count": metrics.total_in_scope,
                    "critical_count": metrics.critical_count,
                    "serious_count": metrics.serious_count,
                    "needs_review_count": metrics.needs_review_count,
                },
            )
            assessment_id = result.scalar_one()

            # 2. Clear previous findings for this assessment before re-inserting
            connection.execute(
                text("DELETE FROM demooc28.compliance_findings WHERE assessment_id = :assessment_id;"),
                {"assessment_id": assessment_id},
            )

            # 3. Insert findings across all evaluated tables
            finding_stmt = text("""
                INSERT INTO demooc28.compliance_findings (
                    assessment_id,
                    table_name,
                    column_name,
                    status,
                    finding_text,
                    recommendation_text,
                    needs_human_review,
                    is_remediated
                ) VALUES (
                    :assessment_id,
                    :table_name,
                    :column_name,
                    :status,
                    :finding_text,
                    :recommendation_text,
                    :needs_human_review,
                    FALSE
                );
            """)

            for finding in findings:
                table_name = getattr(finding, "table_name", None) or (
                    finding.get("table_name") if isinstance(finding, dict) else "unknown_table"
                )
                column_name = getattr(finding, "column_name", None) or (
                    finding.get("column_name") if isinstance(finding, dict) else "unknown_column"
                )
                status = getattr(finding, "status", None) or (
                    finding.get("status") if isinstance(finding, dict) else "Needs review"
                )
                finding_text = getattr(finding, "finding", None) or (
                    finding.get("finding") if isinstance(finding, dict) else ""
                )
                recommendation = getattr(finding, "recommendation", None) or (
                    finding.get("recommendation") if isinstance(finding, dict) else ""
                )

                connection.execute(
                    finding_stmt,
                    {
                        "assessment_id": assessment_id,
                        "table_name": str(table_name),
                        "column_name": str(column_name),
                        "status": str(status),
                        "finding_text": str(finding_text),
                        "recommendation_text": str(recommendation),
                        "needs_human_review": str(status).upper() == "NEEDS REVIEW",
                    },
                )

            return assessment_id

    def get_compliance_results(
        self,
        discovery_run_id: str | UUID,
    ) -> list[dict[str, Any]]:
        """
        Retrieves consolidated compliance assessments and their column findings
        for a given discovery run.
        """
        run_id_str = str(discovery_run_id)

        # assessments_query = text("""
        #     SELECT 
        #         assessment_id,
        #         discovery_run_id,
        #         framework_code,
        #         compliance_score,
        #         risk_band,
        #         in_scope_count,
        #         critical_count,
        #         serious_count,
        #         needs_review_count,
        #         created_at
        #     FROM demooc28.compliance_assessments
        #     WHERE discovery_run_id = :run_id
        #     ORDER BY framework_code;
        # """)
        # 2. Inside get_compliance_results:
        assessments_query = text("""
            SELECT 
                assessment_id,
                discovery_run_id,
                framework_code,
                compliance_score,
                risk_band,
                in_scope_count,
                critical_count,
                serious_count,
                needs_review_count,
                created_at
            FROM demooc28.compliance_assessments
            WHERE discovery_run_id = CAST(:run_id AS UUID)
            ORDER BY framework_code;
        """)

        findings_query = text("""
            SELECT 
                finding_id,
                assessment_id,
                table_name,
                column_name,
                status,
                finding_text,
                recommendation_text,
                needs_human_review,
                is_remediated,
                created_at
            FROM demooc28.compliance_findings
            WHERE assessment_id = :assessment_id
            ORDER BY 
                CASE status 
                    WHEN 'Critical' THEN 1 
                    WHEN 'Serious' THEN 2 
                    ELSE 3 
                END,
                table_name, 
                column_name;
        """)

        results: list[dict[str, Any]] = []

        with self.database.connect() as connection:
            assessment_rows = connection.execute(
                assessments_query,
                {"run_id": run_id_str},
            ).mappings().all()

            for a_row in assessment_rows:
                assessment_data = dict(a_row)
                assessment_id = assessment_data["assessment_id"]

                finding_rows = connection.execute(
                    findings_query,
                    {"assessment_id": assessment_id},
                ).mappings().all()

                assessment_data["findings"] = [dict(f) for f in finding_rows]
                results.append(assessment_data)

        return results