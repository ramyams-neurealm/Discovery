# # # from __future__ import annotations

# # # from typing import Any
# # # from sqlalchemy import text
# # # from src.services.database import MetadataDatabase


# # # class ComplianceRepository:
# # #     def __init__(self, database: MetadataDatabase):
# # #         self.database = database

# # #     def save_framework_assessment(
# # #         self,
# # #         discovery_run_id: str,
# # #         table_name: str,
# # #         framework_result: Any,
# # #     ) -> int:
# # #         """
# # #         Persists assessment summary and individual column findings
# # #         into demooc28.compliance_assessments and demooc28.compliance_findings.
# # #         """
# # #         metrics = framework_result.metrics

# # #         with self.database.transaction() as session:
# # #             # 1. Insert or update the framework assessment header
# # #             assessment_stmt = text("""
# # #                 INSERT INTO demooc28.compliance_assessments (
# # #                     discovery_run_id,
# # #                     framework_code,
# # #                     compliance_score,
# # #                     risk_band,
# # #                     in_scope_count,
# # #                     critical_count,
# # #                     serious_count,
# # #                     needs_review_count
# # #                 ) VALUES (
# # #                     :run_id,
# # #                     :framework_code,
# # #                     :score,
# # #                     :risk_band,
# # #                     :in_scope_count,
# # #                     :critical_count,
# # #                     :serious_count,
# # #                     :needs_review_count
# # #                 )
# # #                 ON CONFLICT (discovery_run_id, framework_code) 
# # #                 DO UPDATE SET
# # #                     compliance_score = EXCLUDED.compliance_score,
# # #                     risk_band = EXCLUDED.risk_band,
# # #                     in_scope_count = EXCLUDED.in_scope_count,
# # #                     critical_count = EXCLUDED.critical_count,
# # #                     serious_count = EXCLUDED.serious_count,
# # #                     needs_review_count = EXCLUDED.needs_review_count,
# # #                     created_at = NOW()
# # #                 RETURNING assessment_id;
# # #             """)

# # #             result = session.execute(
# # #                 assessment_stmt,
# # #                 {
# # #                     "run_id": str(discovery_run_id),
# # #                     "framework_code": framework_result.framework_code,
# # #                     "score": int(round(metrics.score)),
# # #                     "risk_band": str(metrics.risk_band),
# # #                     "in_scope_count": metrics.total_in_scope,
# # #                     "critical_count": metrics.critical_count,
# # #                     "serious_count": metrics.serious_count,
# # #                     "needs_review_count": metrics.needs_review_count,
# # #                 },
# # #             )
# # #             assessment_id = result.scalar_one()

# # #             # 2. Clear old findings for this assessment before re-inserting
# # #             session.execute(
# # #                 text("DELETE FROM demooc28.compliance_findings WHERE assessment_id = :assessment_id;"),
# # #                 {"assessment_id": assessment_id},
# # #             )

# # #             # 3. Insert each column finding
# # #             finding_stmt = text("""
# # #                 INSERT INTO demooc28.compliance_findings (
# # #                     assessment_id,
# # #                     table_name,
# # #                     column_name,
# # #                     status,
# # #                     finding_text,
# # #                     recommendation_text,
# # #                     is_remediated
# # #                 ) VALUES (
# # #                     :assessment_id,
# # #                     :table_name,
# # #                     :column_name,
# # #                     :status,
# # #                     :finding_text,
# # #                     :recommendation_text,
# # #                     FALSE
# # #                 );
# # #             """)

# # #             for finding in framework_result.findings:
# # #                 session.execute(
# # #                     finding_stmt,
# # #                     {
# # #                         "assessment_id": assessment_id,
# # #                         "table_name": table_name,
# # #                         "column_name": finding.column_name,
# # #                         "status": str(finding.status),
# # #                         "finding_text": finding.finding,
# # #                         "recommendation_text": finding.recommendation,
# # #                     },
# # #                 )

# # #             return assessment_id

# # from __future__ import annotations

# # from typing import Any
# # from uuid import UUID
# # from sqlalchemy import text
# # from src.services.database import MetadataDatabase


# # class ComplianceRepository:
# #     def __init__(self, database: MetadataDatabase):
# #         self.database = database

# #     def save_framework_assessment(
# #         self,
# #         discovery_run_id: str | UUID,
# #         framework_code: str,
# #         metrics: Any,
# #         findings: list[Any],
# #     ) -> int:
# #         """
# #         Persists run-level assessment score and all individual column findings
# #         across tables into demooc28.compliance_assessments and demooc28.compliance_findings.
# #         """
# #         run_id_str = str(discovery_run_id)
# #         fw_code = framework_code.upper().strip()

# #         with self.database.transaction() as session:
# #             # 1. Upsert framework assessment header and score
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
# #                     "run_id": run_id_str,
# #                     "framework_code": fw_code,
# #                     "score": int(round(metrics.score)),
# #                     "risk_band": str(getattr(metrics.risk_band, "value", metrics.risk_band)),
# #                     "in_scope_count": metrics.total_in_scope,
# #                     "critical_count": metrics.critical_count,
# #                     "serious_count": metrics.serious_count,
# #                     "needs_review_count": metrics.needs_review_count,
# #                 },
# #             )
# #             assessment_id = result.scalar_one()

# #             # 2. Clear previous findings for this assessment before re-inserting
# #             session.execute(
# #                 text("DELETE FROM demooc28.compliance_findings WHERE assessment_id = :assessment_id;"),
# #                 {"assessment_id": assessment_id},
# #             )

# #             # 3. Insert findings across all evaluated tables
# #             # finding_stmt = text("""
# #             #     INSERT INTO demooc28.compliance_findings (
# #             #         assessment_id,
# #             #         table_name,
# #             #         column_name,
# #             #         status,
# #             #         finding_text,
# #             #         recommendation_text,
# #             #         is_remediated
# #             #     ) VALUES (
# #             #         :assessment_id,
# #             #         :table_name,
# #             #         :column_name,
# #             #         :status,
# #             #         :finding_text,
# #             #         :recommendation_text,
# #             #         FALSE
# #             #     );
# #             # """)

# #             # for finding in findings:
# #             #     table_name = getattr(finding, "table_name", "unknown_table")
# #             #     session.execute(
# #             #         finding_stmt,
# #             #         {
# #             #             "assessment_id": assessment_id,
# #             #             "table_name": table_name,
# #             #             "column_name": finding.column_name,
# #             #             "status": str(finding.status),
# #             #             "finding_text": finding.finding,
# #             #             "recommendation_text": finding.recommendation,
# #             #         },
# #             #     )
# #             finding_stmt = text("""
# #                 INSERT INTO demooc28.compliance_findings (
# #                     assessment_id,
# #                     table_name,
# #                     column_name,
# #                     status,
# #                     finding_text,
# #                     recommendation_text,
# #                     needs_human_review,
# #                     is_remediated
# #                 ) VALUES (
# #                     :assessment_id,
# #                     :table_name,
# #                     :column_name,
# #                     :status,
# #                     :finding_text,
# #                     :recommendation_text,
# #                     :needs_human_review,
# #                     FALSE
# #                 );
# #             """)

# #             for finding in findings:
# #                 table_name = getattr(finding, "table_name", "unknown_table")
# #                 session.execute(
# #                     finding_stmt,
# #                     {
# #                         "assessment_id": assessment_id,
# #                         "table_name": table_name,
# #                         "column_name": finding.column_name,
# #                         "status": str(finding.status),
# #                         "finding_text": finding.finding,
# #                         "recommendation_text": finding.recommendation,
# #                         "needs_human_review": str(finding.status).upper() == "NEEDS REVIEW",
# #                     },
# #                 )
# #             return assessment_id

# #     def get_compliance_results(
# #         self,
# #         discovery_run_id: str | UUID,
# #     ) -> list[dict[str, Any]]:
# #         """
# #         Retrieves consolidated compliance assessments and their column findings
# #         for a given discovery run.
# #         """
# #         run_id_str = str(discovery_run_id)

# #         assessments_query = text("""
# #             SELECT 
# #                 assessment_id,
# #                 discovery_run_id,
# #                 framework_code,
# #                 compliance_score,
# #                 risk_band,
# #                 in_scope_count,
# #                 critical_count,
# #                 serious_count,
# #                 needs_review_count,
# #                 created_at
# #             FROM demooc28.compliance_assessments
# #             WHERE discovery_run_id = :run_id
# #             ORDER BY framework_code;
# #         """)

# #         findings_query = text("""
# #             SELECT 
# #                 finding_id,
# #                 assessment_id,
# #                 table_name,
# #                 column_name,
# #                 status,
# #                 finding_text,
# #                 recommendation_text,
# #                 is_remediated,
# #                 created_at
# #             FROM demooc28.compliance_findings
# #             WHERE assessment_id = :assessment_id
# #             ORDER BY 
# #                 CASE status 
# #                     WHEN 'Critical' THEN 1 
# #                     WHEN 'Serious' THEN 2 
# #                     ELSE 3 
# #                 END,
# #                 table_name, 
# #                 column_name;
# #         """)

# #         results: list[dict[str, Any]] = []

# #         with self.database.connect() as connection:
# #             assessment_rows = connection.execute(
# #                 assessments_query,
# #                 {"run_id": run_id_str},
# #             ).mappings().all()

# #             for a_row in assessment_rows:
# #                 assessment_data = dict(a_row)
# #                 assessment_id = assessment_data["assessment_id"]

# #                 finding_rows = connection.execute(
# #                     findings_query,
# #                     {"assessment_id": assessment_id},
# #                 ).mappings().all()

# #                 assessment_data["findings"] = [dict(f) for f in finding_rows]
# #                 results.append(assessment_data)

# #         return results

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

#         # MetadataDatabase uses .connect() context manager across this project
#         with self.database.connect() as connection:
#             # 1. Upsert framework assessment header and score
#             # assessment_stmt = text("""
#             #     INSERT INTO demooc28.compliance_assessments (
#             #         discovery_run_id,
#             #         framework_code,
#             #         compliance_score,
#             #         risk_band,
#             #         in_scope_count,
#             #         critical_count,
#             #         serious_count,
#             #         needs_review_count
#             #     ) VALUES (
#             #         :run_id,
#             #         :framework_code,
#             #         :score,
#             #         :risk_band,
#             #         :in_scope_count,
#             #         :critical_count,
#             #         :serious_count,
#             #         :needs_review_count
#             #     )
#             #     ON CONFLICT (discovery_run_id, framework_code) 
#             #     DO UPDATE SET
#             #         compliance_score = EXCLUDED.compliance_score,
#             #         risk_band = EXCLUDED.risk_band,
#             #         in_scope_count = EXCLUDED.in_scope_count,
#             #         critical_count = EXCLUDED.critical_count,
#             #         serious_count = EXCLUDED.serious_count,
#             #         needs_review_count = EXCLUDED.needs_review_count,
#             #         created_at = NOW()
#             #     RETURNING assessment_id;
#             # """)
#             # 1. Inside save_framework_assessment:
#             assessment_stmt = text("""
#                 INSERT INTO demooc28.compliance_assessments (
#                     discovery_run_id,
#                     framework_code,
#                     compliance_score,
#                     risk_band,
#                     assessment_status,
#                     good_count,
#                     in_scope_count,
#                     critical_count,
#                     serious_count,
#                     needs_review_count
#                 ) VALUES (
#                     CAST(:run_id AS UUID),
#                     :framework_code,
#                     :score,
#                     :risk_band,
#                     :assessment_status,
#                     :good_count,
#                     :in_scope_count,
#                     :critical_count,
#                     :serious_count,
#                     :needs_review_count
#                 )
#                 ON CONFLICT (discovery_run_id, framework_code) 
#                 DO UPDATE SET
#                     compliance_score = EXCLUDED.compliance_score,
#                     risk_band = EXCLUDED.risk_band,
#                     assessment_status = EXCLUDED.assessment_status,
#                     good_count = EXCLUDED.good_count,
#                     in_scope_count = EXCLUDED.in_scope_count,
#                     critical_count = EXCLUDED.critical_count,
#                     serious_count = EXCLUDED.serious_count,
#                     needs_review_count = EXCLUDED.needs_review_count,
#                     created_at = NOW()
#                 RETURNING assessment_id;
#             """)
#             result = connection.execute(
#                 assessment_stmt,
#                 {
#     "run_id": run_id_str,
#     "framework_code": fw_code,
#     "score": (
#         int(round(metrics.score))
#         if metrics.score is not None
#         else None
#     ),
#     "risk_band": str(
#         getattr(
#             metrics.risk_band,
#             "value",
#             metrics.risk_band,
#         )
#     ),
#     "assessment_status": str(
#         getattr(
#             metrics.assessment_status,
#             "value",
#             metrics.assessment_status,
#         )
#     ),
#     "good_count": metrics.good_count,
#     "in_scope_count": metrics.total_in_scope,
#     "critical_count": metrics.critical_count,
#     "serious_count": metrics.serious_count,
#     "needs_review_count": metrics.needs_review_count,
# },
#             )
#             assessment_id = result.scalar_one()

#             # 2. Clear previous findings for this assessment before re-inserting
#             connection.execute(
#                 text("DELETE FROM demooc28.compliance_findings WHERE assessment_id = :assessment_id;"),
#                 {"assessment_id": assessment_id},
#             )

#             # 3. Insert findings across all evaluated tables
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
#                 table_name = getattr(finding, "table_name", None) or (
#                     finding.get("table_name") if isinstance(finding, dict) else "unknown_table"
#                 )
#                 column_name = getattr(finding, "column_name", None) or (
#                     finding.get("column_name") if isinstance(finding, dict) else "unknown_column"
#                 )
#                 status = getattr(finding, "status", None) or (
#                     finding.get("status") if isinstance(finding, dict) else "Needs review"
#                 )
#                 finding_text = getattr(finding, "finding", None) or (
#                     finding.get("finding") if isinstance(finding, dict) else ""
#                 )
#                 recommendation = getattr(finding, "recommendation", None) or (
#                     finding.get("recommendation") if isinstance(finding, dict) else ""
#                 )

#                 connection.execute(
#                     finding_stmt,
#                     {
#                         "assessment_id": assessment_id,
#                         "table_name": str(table_name),
#                         "column_name": str(column_name),
#                         "status": str(status),
#                         "finding_text": str(finding_text),
#                         "recommendation_text": str(recommendation),
#                         "needs_human_review": str(status).upper() == "NEEDS REVIEW",
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

#         # assessments_query = text("""
#         #     SELECT 
#         #         assessment_id,
#         #         discovery_run_id,
#         #         framework_code,
#         #         compliance_score,
#         #         risk_band,
#         #         in_scope_count,
#         #         critical_count,
#         #         serious_count,
#         #         needs_review_count,
#         #         created_at
#         #     FROM demooc28.compliance_assessments
#         #     WHERE discovery_run_id = :run_id
#         #     ORDER BY framework_code;
#         # """)
#         # 2. Inside get_compliance_results:
#         assessments_query = text("""
#             SELECT 
#                 assessment_id,
#                 discovery_run_id,
#                 framework_code,
#                 compliance_score,
#                 risk_band,
#                 assessment_status,
#                 good_count,
#                 in_scope_count,
#                 critical_count,
#                 serious_count,
#                 needs_review_count,
#                 created_at
#             FROM demooc28.compliance_assessments
#             WHERE discovery_run_id = CAST(:run_id AS UUID)
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
#                 needs_human_review,
#                 is_remediated,
#                 remediation_status,
#                 remediation_action,
#                 remediated_by,
#                 remediated_at,
#                 remediation_notes,
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

#     def remediate_finding_across_frameworks(
#         self,
#         discovery_run_id: UUID | str,
#         table_name: str,
#         column_name: str,
#         remediation_action: str,
#         remediation_status: str = "REMEDIATED_PENDING_VERIFICATION",
#         remediated_by: str | None = None,
#         remediation_notes: str | None = None,
#     ) -> dict[str, Any]:
#         """Update finding remediation lifecycle across frameworks and recalculate metrics safely.

#         Governance rule:
#         - Only VERIFIED findings count as Good in framework score recalculations.
#         - REMEDIATED_PENDING_VERIFICATION, IN_PROGRESS, and ACCEPTED_RISK preserve original risk weight
#           while recording full remediation/governance audit metadata.
#         """
#         from types import SimpleNamespace
#         from src.services.compliance_service import calculate_metrics

#         run_id_str = str(discovery_run_id)
#         clean_table = table_name.strip()
#         clean_col = column_name.strip()
#         clean_action = remediation_action.strip()
#         clean_lifecycle = str(getattr(remediation_status, "value", remediation_status)).strip().upper()
#         is_verified = clean_lifecycle == "VERIFIED"

#         find_targets_stmt = text("""
#             SELECT
#                 f.finding_id,
#                 f.assessment_id,
#                 a.framework_code,
#                 f.status AS original_status
#             FROM demooc28.compliance_findings f
#             JOIN demooc28.compliance_assessments a
#               ON a.assessment_id = f.assessment_id
#             WHERE a.discovery_run_id = CAST(:run_id AS UUID)
#               AND LOWER(f.table_name) = LOWER(:table_name)
#               AND LOWER(f.column_name) = LOWER(:column_name)
#             ORDER BY a.framework_code;
#         """)

#         update_finding_stmt = text("""
#             UPDATE demooc28.compliance_findings
#             SET
#                 remediation_status = :remediation_status,
#                 is_remediated = :is_remediated,
#                 remediation_action = :remediation_action,
#                 remediated_by = :remediated_by,
#                 remediated_at = NOW(),
#                 remediation_notes = :remediation_notes
#             WHERE finding_id = :finding_id
#             RETURNING remediated_at;
#         """)

#         all_findings_stmt = text("""
#             SELECT
#                 finding_id,
#                 status,
#                 is_remediated,
#                 remediation_status
#             FROM demooc28.compliance_findings
#             WHERE assessment_id = :assessment_id;
#         """)

#         update_assessment_stmt = text("""
#             UPDATE demooc28.compliance_assessments
#             SET
#                 compliance_score = :score,
#                 risk_band = :risk_band,
#                 assessment_status = :assessment_status,
#                 good_count = :good_count,
#                 in_scope_count = :in_scope_count,
#                 critical_count = :critical_count,
#                 serious_count = :serious_count,
#                 needs_review_count = :needs_review_count
#             WHERE assessment_id = :assessment_id;
#         """)

#         with self.database.engine.begin() as connection:
#             targets = connection.execute(
#                 find_targets_stmt,
#                 {
#                     "run_id": run_id_str,
#                     "table_name": clean_table,
#                     "column_name": clean_col,
#                 },
#             ).mappings().all()

#             if not targets:
#                 return {
#                     "discovery_run_id": run_id_str,
#                     "table_name": clean_table,
#                     "column_name": clean_col,
#                     "remediated_findings_count": 0,
#                     "frameworks_updated": [],
#                 }

#             frameworks_updated: list[dict[str, Any]] = []

#             for target in targets:
#                 finding_id = target["finding_id"]
#                 assessment_id = target["assessment_id"]
#                 fw_code = target["framework_code"]

#                 remediated_at_val = connection.execute(
#                     update_finding_stmt,
#                     {
#                         "finding_id": finding_id,
#                         "remediation_status": clean_lifecycle,
#                         "is_remediated": is_verified,
#                         "remediation_action": clean_action,
#                         "remediated_by": remediated_by,
#                         "remediation_notes": remediation_notes,
#                     },
#                 ).scalar_one()

#                 # Only VERIFIED findings improve the score; pending/accepted preserve original risk weight
#                 sibling_rows = connection.execute(
#                     all_findings_stmt,
#                     {"assessment_id": assessment_id},
#                 ).mappings().all()

#                 effective_evals = [
#                     SimpleNamespace(
#                         status=(
#                             "Good"
#                             if (
#                                 row.get("remediation_status") == "VERIFIED"
#                                 or (row.get("remediation_status") is None and row["is_remediated"])
#                             )
#                             else row["status"]
#                         )
#                     )
#                     for row in sibling_rows
#                 ]
#                 metrics = calculate_metrics(effective_evals)

#                 connection.execute(
#                     update_assessment_stmt,
#                     {
#                         "assessment_id": assessment_id,
#                         "score": int(round(metrics.score)) if metrics.score is not None else None,
#                         "risk_band": str(getattr(metrics.risk_band, "value", metrics.risk_band)),
#                         "assessment_status": str(
#                             getattr(metrics.assessment_status, "value", metrics.assessment_status)
#                         ),
#                         "good_count": metrics.good_count,
#                         "in_scope_count": metrics.total_in_scope,
#                         "critical_count": metrics.critical_count,
#                         "serious_count": metrics.serious_count,
#                         "needs_review_count": metrics.needs_review_count,
#                     },
#                 )

#                 frameworks_updated.append({
#                     "framework_code": fw_code,
#                     "finding_id": finding_id,
#                     "original_status": target["original_status"],
#                     "remediation_status": clean_lifecycle,
#                     "is_remediated": is_verified,
#                     "remediation_action": clean_action,
#                     "remediated_by": remediated_by,
#                     "remediated_at": remediated_at_val.isoformat() if remediated_at_val else None,
#                     "updated_metrics": metrics.model_dump(),
#                 })

#             return {
#                 "discovery_run_id": run_id_str,
#                 "table_name": clean_table,
#                 "column_name": clean_col,
#                 "remediated_findings_count": len(frameworks_updated),
#                 "frameworks_updated": frameworks_updated,
#             }





from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone
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

        with self.database.connect() as connection:
            assessment_stmt = text("""
                INSERT INTO demooc28.compliance_assessments (
                    discovery_run_id,
                    framework_code,
                    compliance_score,
                    risk_band,
                    assessment_status,
                    good_count,
                    in_scope_count,
                    critical_count,
                    serious_count,
                    needs_review_count
                ) VALUES (
                    CAST(:run_id AS UUID),
                    :framework_code,
                    :score,
                    :risk_band,
                    :assessment_status,
                    :good_count,
                    :in_scope_count,
                    :critical_count,
                    :serious_count,
                    :needs_review_count
                )
                ON CONFLICT (discovery_run_id, framework_code) 
                DO UPDATE SET
                    compliance_score = EXCLUDED.compliance_score,
                    risk_band = EXCLUDED.risk_band,
                    assessment_status = EXCLUDED.assessment_status,
                    good_count = EXCLUDED.good_count,
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
                    "score": (
                        int(round(metrics.score))
                        if metrics.score is not None
                        else None
                    ),
                    "risk_band": str(
                        getattr(
                            metrics.risk_band,
                            "value",
                            metrics.risk_band,
                        )
                    ),
                    "assessment_status": str(
                        getattr(
                            metrics.assessment_status,
                            "value",
                            metrics.assessment_status,
                        )
                    ),
                    "good_count": metrics.good_count,
                    "in_scope_count": metrics.total_in_scope,
                    "critical_count": metrics.critical_count,
                    "serious_count": metrics.serious_count,
                    "needs_review_count": metrics.needs_review_count,
                },
            )
            assessment_id = result.scalar_one()

            # Clear previous findings for this assessment before re-inserting
            connection.execute(
                text("DELETE FROM demooc28.compliance_findings WHERE assessment_id = :assessment_id;"),
                {"assessment_id": assessment_id},
            )

            # Insert findings across all evaluated tables
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
        (enriched with column classification category & subtype) for a discovery run.
        """
        run_id_str = str(discovery_run_id)

        assessments_query = text("""
            SELECT 
                assessment_id,
                discovery_run_id,
                framework_code,
                compliance_score,
                risk_band,
                assessment_status,
                good_count,
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
                remediation_status,
                remediation_action,
                remediated_by,
                remediated_at,
                remediation_notes,
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

        classifications_query = text("""
            SELECT
                LOWER(obj.object_name) AS table_key,
                LOWER(col.column_name) AS column_key,
                cls.display_classification,
                cls.sensitive_data_type
            FROM demooc28.column_classifications AS cls
            JOIN demooc28.discovered_columns AS col
              ON col.column_id = cls.column_id
            JOIN demooc28.discovered_objects AS obj
              ON obj.object_id = col.object_id
            WHERE cls.discovery_run_id = CAST(:run_id AS UUID);
        """)

        results: list[dict[str, Any]] = []

        with self.database.connect() as connection:
            classification_rows = connection.execute(
                classifications_query,
                {"run_id": run_id_str},
            ).mappings().all()

            classification_lookup: dict[tuple[str, str], dict[str, Any]] = {
                (str(c["table_key"]), str(c["column_key"])): {
                    "display_classification": c["display_classification"],
                    "sensitive_data_type": c["sensitive_data_type"],
                }
                for c in classification_rows
            }

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

                enriched_findings: list[dict[str, Any]] = []
                for f in finding_rows:
                    finding_dict = dict(f)
                    lookup_key = (
                        str(finding_dict.get("table_name") or "").lower().strip(),
                        str(finding_dict.get("column_name") or "").lower().strip(),
                    )
                    cls_meta = classification_lookup.get(lookup_key, {})
                    finding_dict["display_classification"] = cls_meta.get(
                        "display_classification"
                    )
                    finding_dict["sensitive_data_type"] = cls_meta.get(
                        "sensitive_data_type"
                    )
                    enriched_findings.append(finding_dict)

                assessment_data["findings"] = enriched_findings
                results.append(assessment_data)

        return results

    def get_remediation_standards(self) -> dict[str, Any]:
        """Return organization remediation SLA and governance standards."""
        defaults: dict[str, Any] = {
            "critical_sla_days": 3,
            "serious_sla_days": 14,
            "needs_review_sla_days": 30,
            "min_justification_chars": 40,
            "require_lead_signoff": True,
            "preferred_fixes": {
                "PHI": "Tokenization (vault-backed, last 4 digits visible)",
                "PII": "AES-256 column-level encryption with RBAC",
                "SENSITIVE": "Cryptographic hashing (Argon2id / bcrypt) + access restriction",
                "FINANCIAL": "PCI-compliant vault tokenization",
                "DEFAULT": "Apply column-level encryption and role-based access control",
            },
            "updated_by": None,
            "updated_at": None,
        }

        query = text("""
            SELECT
                critical_sla_days,
                serious_sla_days,
                needs_review_sla_days,
                min_justification_chars,
                require_lead_signoff,
                preferred_fixes,
                updated_by,
                updated_at
            FROM demooc28.remediation_standards
            WHERE standard_id = 1;
        """)

        try:
            with self.database.connect() as connection:
                row = connection.execute(query).mappings().first()
                if not row:
                    return defaults
                data = dict(row)
                if isinstance(data.get("preferred_fixes"), str):
                    data["preferred_fixes"] = json.loads(data["preferred_fixes"])
                elif not data.get("preferred_fixes"):
                    data["preferred_fixes"] = defaults["preferred_fixes"]
                if data.get("updated_at") is not None:
                    data["updated_at"] = data["updated_at"].isoformat()
                return data
        except Exception:
            return defaults

    def update_remediation_standards(
        self,
        *,
        critical_sla_days: int | None = None,
        serious_sla_days: int | None = None,
        needs_review_sla_days: int | None = None,
        min_justification_chars: int | None = None,
        require_lead_signoff: bool | None = None,
        preferred_fixes: dict[str, str] | None = None,
        updated_by: str | None = None,
    ) -> dict[str, Any]:
        """Update editable organization remediation SLA and risk-acceptance rules."""
        current = self.get_remediation_standards()
        merged_fixes = dict(current.get("preferred_fixes") or {})
        if preferred_fixes:
            for key, value in preferred_fixes.items():
                if value and str(value).strip():
                    merged_fixes[str(key).strip().upper()] = str(value).strip()

        upsert_stmt = text("""
            INSERT INTO demooc28.remediation_standards (
                standard_id,
                critical_sla_days,
                serious_sla_days,
                needs_review_sla_days,
                min_justification_chars,
                require_lead_signoff,
                preferred_fixes,
                updated_by,
                updated_at
            )
            VALUES (
                1,
                :critical_sla_days,
                :serious_sla_days,
                :needs_review_sla_days,
                :min_justification_chars,
                :require_lead_signoff,
                CAST(:preferred_fixes AS JSONB),
                :updated_by,
                NOW()
            )
            ON CONFLICT (standard_id) DO UPDATE SET
                critical_sla_days = EXCLUDED.critical_sla_days,
                serious_sla_days = EXCLUDED.serious_sla_days,
                needs_review_sla_days = EXCLUDED.needs_review_sla_days,
                min_justification_chars = EXCLUDED.min_justification_chars,
                require_lead_signoff = EXCLUDED.require_lead_signoff,
                preferred_fixes = EXCLUDED.preferred_fixes,
                updated_by = EXCLUDED.updated_by,
                updated_at = NOW();
        """)

        with self.database.engine.begin() as connection:
            connection.execute(
                upsert_stmt,
                {
                    "critical_sla_days": (
                        critical_sla_days
                        if critical_sla_days is not None
                        else current["critical_sla_days"]
                    ),
                    "serious_sla_days": (
                        serious_sla_days
                        if serious_sla_days is not None
                        else current["serious_sla_days"]
                    ),
                    "needs_review_sla_days": (
                        needs_review_sla_days
                        if needs_review_sla_days is not None
                        else current["needs_review_sla_days"]
                    ),
                    "min_justification_chars": (
                        min_justification_chars
                        if min_justification_chars is not None
                        else current["min_justification_chars"]
                    ),
                    "require_lead_signoff": (
                        require_lead_signoff
                        if require_lead_signoff is not None
                        else current["require_lead_signoff"]
                    ),
                    "preferred_fixes": json.dumps(merged_fixes),
                    "updated_by": updated_by,
                },
            )

        return self.get_remediation_standards()

    def get_remediation_workspace(
        self,
        discovery_run_id: UUID | str,
        *,
        status_filter: str | None = None,
        search: str | None = None,
    ) -> dict[str, Any]:
        """Return deduplicated column-level remediation queue, KPI summary cards, and Org SLA rules."""
        run_id_str = str(discovery_run_id)
        standards = self.get_remediation_standards()
        today = date.today()

        findings_query = text("""
            SELECT
                f.finding_id,
                f.assessment_id,
                a.framework_code,
                f.table_name,
                f.column_name,
                f.status,
                f.finding_text,
                f.recommendation_text,
                f.is_remediated,
                COALESCE(f.remediation_status, 'OPEN') AS remediation_status,
                f.remediation_action,
                f.remediated_by,
                f.remediated_at,
                f.remediation_notes,
                f.assigned_to,
                f.due_date,
                f.approved_by,
                COALESCE(f.activity_log, '[]'::jsonb) AS activity_log,
                f.created_at
            FROM demooc28.compliance_findings f
            JOIN demooc28.compliance_assessments a
              ON a.assessment_id = f.assessment_id
            WHERE a.discovery_run_id = CAST(:run_id AS UUID)
              AND LOWER(f.status) != 'good'
            ORDER BY f.table_name, f.column_name, a.framework_code;
        """)

        classifications_query = text("""
            SELECT
                LOWER(obj.object_name) AS table_key,
                LOWER(col.column_name) AS column_key,
                cls.display_classification,
                cls.sensitive_data_type
            FROM demooc28.column_classifications AS cls
            JOIN demooc28.discovered_columns AS col
              ON col.column_id = cls.column_id
            JOIN demooc28.discovered_objects AS obj
              ON obj.object_id = col.object_id
            WHERE cls.discovery_run_id = CAST(:run_id AS UUID);
        """)

        with self.database.connect() as connection:
            classification_rows = connection.execute(
                classifications_query,
                {"run_id": run_id_str},
            ).mappings().all()

            classification_lookup: dict[tuple[str, str], dict[str, Any]] = {
                (str(c["table_key"]), str(c["column_key"])): {
                    "display_classification": c["display_classification"],
                    "sensitive_data_type": c["sensitive_data_type"],
                }
                for c in classification_rows
            }

            raw_rows = connection.execute(
                findings_query,
                {"run_id": run_id_str},
            ).mappings().all()

        severity_rank = {"critical": 1, "serious": 2, "needs review": 3}
        framework_short_map = {
            "HIPAA": "H",
            "GDPR": "G",
            "DPDP": "D",
            "CCPA_CPRA": "C",
            "CCPA": "C",
            "PCI_DSS": "P",
        }
        framework_label_map = {
            "HIPAA": "HIPAA",
            "GDPR": "GDPR",
            "DPDP": "DPDP",
            "CCPA_CPRA": "CCPA/CPRA",
            "PCI_DSS": "PCI-DSS",
        }

        grouped: dict[tuple[str, str], dict[str, Any]] = {}
        for row in raw_rows:
            r = dict(row)
            key = (
                str(r["table_name"]).strip().lower(),
                str(r["column_name"]).strip().lower(),
            )
            cls_meta = classification_lookup.get(key, {})
            classification = cls_meta.get("display_classification") or "Sensitive"
            preferred_fixes = standards.get("preferred_fixes") or {}
            org_fix = (
                preferred_fixes.get(classification.upper())
                or preferred_fixes.get("DEFAULT")
                or "Apply column-level encryption and role-based access control"
            )

            if key not in grouped:
                grouped[key] = {
                    "table_name": str(r["table_name"]).strip(),
                    "column_name": str(r["column_name"]).strip(),
                    "column": f"{str(r['table_name']).strip()}.{str(r['column_name']).strip()}",
                    "classification": classification,
                    "sensitive_data_type": cls_meta.get("sensitive_data_type"),
                    "org_preferred_fix": org_fix,
                    "frameworks": [],
                    "framework_badges": [],
                    "highest_severity": str(r["status"]),
                    "remediation_status": str(r.get("remediation_status") or "OPEN").upper(),
                    "remediation_action": r.get("remediation_action"),
                    "remediated_by": r.get("remediated_by"),
                    "remediated_at": r.get("remediated_at"),
                    "remediation_notes": r.get("remediation_notes"),
                    "assigned_to": r.get("assigned_to"),
                    "explicit_due_date": r.get("due_date"),
                    "approved_by": r.get("approved_by"),
                    "activity": [],
                    "created_at": r.get("created_at"),
                    "findings": [],
                }

            entry = grouped[key]
            fw_code = str(r["framework_code"]).strip().upper()
            if fw_code not in entry["frameworks"]:
                entry["frameworks"].append(fw_code)
                entry["framework_badges"].append({
                    "code": fw_code,
                    "short": framework_short_map.get(fw_code, fw_code[:1]),
                    "label": framework_label_map.get(fw_code, fw_code),
                    "severity": str(r["status"]),
                })

            current_rank = severity_rank.get(entry["highest_severity"].lower(), 99)
            new_rank = severity_rank.get(str(r["status"]).lower(), 99)
            if new_rank < current_rank:
                entry["highest_severity"] = str(r["status"])

            row_status = str(r.get("remediation_status") or "OPEN").upper()
            if row_status != "OPEN":
                entry["remediation_status"] = row_status
            if r.get("assigned_to"):
                entry["assigned_to"] = r["assigned_to"]
            if r.get("due_date"):
                entry["explicit_due_date"] = r["due_date"]
            if r.get("approved_by"):
                entry["approved_by"] = r["approved_by"]
            if r.get("remediation_action"):
                entry["remediation_action"] = r["remediation_action"]
            if r.get("remediated_by"):
                entry["remediated_by"] = r["remediated_by"]
            if r.get("remediated_at"):
                entry["remediated_at"] = r["remediated_at"]
            if r.get("remediation_notes"):
                entry["remediation_notes"] = r["remediation_notes"]

            raw_activity = r.get("activity_log")
            if isinstance(raw_activity, str):
                raw_activity = json.loads(raw_activity)
            if isinstance(raw_activity, list) and len(raw_activity) > len(entry["activity"]):
                entry["activity"] = raw_activity

            entry["findings"].append({
                "finding_id": r["finding_id"],
                "framework_code": fw_code,
                "framework_label": framework_label_map.get(fw_code, fw_code),
                "severity": str(r["status"]),
                "finding_text": r["finding_text"],
                "recommendation_text": r["recommendation_text"],
            })

        all_items: list[dict[str, Any]] = []
        open_count = 0
        in_progress_count = 0
        resolved_count = 0
        risk_accepted_count = 0
        overdue_count = 0

        for entry in grouped.values():
            sev_lower = entry["highest_severity"].lower()
            if sev_lower == "critical":
                sla_days = int(standards["critical_sla_days"])
            elif sev_lower == "serious":
                sla_days = int(standards["serious_sla_days"])
            else:
                sla_days = int(standards["needs_review_sla_days"])

            explicit_due = entry["explicit_due_date"]
            if isinstance(explicit_due, datetime):
                due_dt = explicit_due.date()
            elif isinstance(explicit_due, date):
                due_dt = explicit_due
            elif isinstance(explicit_due, str) and explicit_due.strip():
                due_dt = date.fromisoformat(explicit_due.strip()[:10])
            else:
                created_raw = entry["created_at"]
                base_date = (
                    created_raw.date()
                    if isinstance(created_raw, datetime)
                    else (created_raw if isinstance(created_raw, date) else today)
                )
                due_dt = base_date + timedelta(days=sla_days)

            lifecycle = entry["remediation_status"]
            if lifecycle in {"VERIFIED", "REMEDIATED_PENDING_VERIFICATION"}:
                display_status = "Resolved"
                resolved_count += 1
            elif lifecycle == "ACCEPTED_RISK":
                display_status = "Risk accepted"
                risk_accepted_count += 1
            elif lifecycle == "IN_PROGRESS":
                display_status = "In progress"
                in_progress_count += 1
            else:
                lifecycle = "OPEN"
                display_status = "Open"
                open_count += 1

            is_overdue = lifecycle in {"OPEN", "IN_PROGRESS"} and due_dt < today
            if is_overdue:
                overdue_count += 1

            remediated_at_val = entry["remediated_at"]
            all_items.append({
                "table_name": entry["table_name"],
                "column_name": entry["column_name"],
                "column": entry["column"],
                "classification": entry["classification"],
                "sensitive_data_type": entry["sensitive_data_type"],
                "frameworks": entry["frameworks"],
                "framework_badges": entry["framework_badges"],
                "severity": entry["highest_severity"],
                "remediation_status": lifecycle,
                "display_status": display_status,
                "sla_days": sla_days,
                "due_date": due_dt.isoformat(),
                "is_overdue": is_overdue,
                "owner": entry["assigned_to"],
                "org_preferred_fix": entry["org_preferred_fix"],
                "remediation_action": entry["remediation_action"],
                "remediated_by": entry["remediated_by"],
                "remediated_at": (
                    remediated_at_val.isoformat()
                    if isinstance(remediated_at_val, datetime)
                    else remediated_at_val
                ),
                "approved_by": entry["approved_by"],
                "remediation_notes": entry["remediation_notes"],
                "findings": entry["findings"],
                "activity": entry["activity"],
            })

        all_items.sort(
            key=lambda item: (
                severity_rank.get(item["severity"].lower(), 99),
                item["column"].lower(),
            )
        )

        total_items = len(all_items)
        completed_items = resolved_count + risk_accepted_count
        progress_pct = round((completed_items / total_items) * 100) if total_items > 0 else 0

        filtered_items = all_items
        if status_filter and status_filter.strip().upper() not in {"", "ALL"}:
            norm_filter = status_filter.strip().upper().replace(" ", "_")
            if norm_filter == "RESOLVED":
                filtered_items = [
                    i
                    for i in filtered_items
                    if i["remediation_status"] in {"VERIFIED", "REMEDIATED_PENDING_VERIFICATION"}
                ]
            elif norm_filter in {"RISK_ACCEPTED", "ACCEPTED_RISK"}:
                filtered_items = [
                    i for i in filtered_items if i["remediation_status"] == "ACCEPTED_RISK"
                ]
            elif norm_filter == "OVERDUE":
                filtered_items = [i for i in filtered_items if i["is_overdue"]]
            else:
                filtered_items = [
                    i for i in filtered_items if i["remediation_status"] == norm_filter
                ]

        if search and search.strip():
            needle = search.strip().lower()
            filtered_items = [
                i
                for i in filtered_items
                if needle in i["column"].lower()
                or needle in i["classification"].lower()
                or (i["owner"] and needle in i["owner"].lower())
            ]

        return {
            "discovery_run_id": run_id_str,
            "summary": {
                "remediation_progress_pct": progress_pct,
                "total_items": total_items,
                "open_count": open_count,
                "in_progress_count": in_progress_count,
                "resolved_count": resolved_count,
                "risk_accepted_count": risk_accepted_count,
                "overdue_count": overdue_count,
            },
            "organization_standards": standards,
            "items": filtered_items,
        }

    def remediate_finding_across_frameworks(
        self,
        discovery_run_id: UUID | str,
        table_name: str,
        column_name: str,
        remediation_action: str | None = None,
        remediation_status: str | None = None,
        remediated_by: str | None = None,
        remediation_notes: str | None = None,
        action_type: str | None = None,
        assigned_to: str | None = None,
        due_date: str | None = None,
        justification: str | None = None,
        approved_by: str | None = None,
    ) -> dict[str, Any]:
        """Execute any of the 4 Remediation modal actions across all frameworks for a column."""
        from types import SimpleNamespace
        from src.services.compliance_service import calculate_metrics

        run_id_str = str(discovery_run_id)
        clean_table = table_name.strip()
        clean_col = column_name.strip()
        clean_action_type = (
            str(getattr(action_type, "value", action_type)).strip().upper()
            if action_type
            else None
        )
        standards = self.get_remediation_standards()

        find_targets_stmt = text("""
            SELECT
                f.finding_id,
                f.assessment_id,
                a.framework_code,
                f.status AS original_status,
                f.assigned_to,
                f.due_date,
                f.approved_by,
                COALESCE(f.activity_log, '[]'::jsonb) AS activity_log
            FROM demooc28.compliance_findings f
            JOIN demooc28.compliance_assessments a
              ON a.assessment_id = f.assessment_id
            WHERE a.discovery_run_id = CAST(:run_id AS UUID)
              AND LOWER(f.table_name) = LOWER(:table_name)
              AND LOWER(f.column_name) = LOWER(:column_name)
            ORDER BY a.framework_code;
        """)

        cls_stmt = text("""
            SELECT cls.display_classification
            FROM demooc28.column_classifications cls
            JOIN demooc28.discovered_columns col ON col.column_id = cls.column_id
            JOIN demooc28.discovered_objects obj ON obj.object_id = col.object_id
            WHERE cls.discovery_run_id = CAST(:run_id AS UUID)
              AND LOWER(obj.object_name) = LOWER(:table_name)
              AND LOWER(col.column_name) = LOWER(:column_name)
            LIMIT 1;
        """)

        update_finding_stmt = text("""
            UPDATE demooc28.compliance_findings
            SET
                remediation_status = :remediation_status,
                is_remediated = :is_remediated,
                remediation_action = :remediation_action,
                remediated_by = :remediated_by,
                remediated_at = NOW(),
                remediation_notes = :remediation_notes,
                assigned_to = :assigned_to,
                due_date = CAST(:due_date AS DATE),
                approved_by = :approved_by,
                activity_log = CAST(:activity_log AS JSONB)
            WHERE finding_id = :finding_id
            RETURNING remediated_at;
        """)

        all_findings_stmt = text("""
            SELECT
                finding_id,
                status,
                is_remediated,
                remediation_status
            FROM demooc28.compliance_findings
            WHERE assessment_id = :assessment_id;
        """)

        update_assessment_stmt = text("""
            UPDATE demooc28.compliance_assessments
            SET
                compliance_score = :score,
                risk_band = :risk_band,
                assessment_status = :assessment_status,
                good_count = :good_count,
                in_scope_count = :in_scope_count,
                critical_count = :critical_count,
                serious_count = :serious_count,
                needs_review_count = :needs_review_count
            WHERE assessment_id = :assessment_id;
        """)

        with self.database.engine.begin() as connection:
            targets = connection.execute(
                find_targets_stmt,
                {
                    "run_id": run_id_str,
                    "table_name": clean_table,
                    "column_name": clean_col,
                },
            ).mappings().all()

            if not targets:
                return {
                    "discovery_run_id": run_id_str,
                    "table_name": clean_table,
                    "column_name": clean_col,
                    "remediated_findings_count": 0,
                    "frameworks_updated": [],
                }

            display_cls = connection.execute(
                cls_stmt,
                {
                    "run_id": run_id_str,
                    "table_name": clean_table,
                    "column_name": clean_col,
                },
            ).scalar()
            classification_key = str(display_cls or "DEFAULT").strip().upper()
            preferred_fixes = standards.get("preferred_fixes") or {}
            org_fix = (
                preferred_fixes.get(classification_key)
                or preferred_fixes.get("DEFAULT")
                or "Apply column-level encryption and role-based access control"
            )

            severities = {str(t["original_status"]).strip().lower() for t in targets}
            has_critical = "critical" in severities
            has_serious = "serious" in severities

            clean_notes = (justification or remediation_notes or "").strip() or None
            clean_approved_by = (approved_by or "").strip() or None
            clean_assigned_to = (assigned_to or "").strip() or None

            if clean_action_type == "ACCEPT_RISK":
                min_chars = int(standards.get("min_justification_chars", 40))
                if not clean_notes or len(clean_notes) < min_chars:
                    raise ValueError(
                        f"Risk acceptance justification must be at least {min_chars} characters."
                    )
                if standards.get("require_lead_signoff", True) and (has_critical or has_serious):
                    if not clean_approved_by:
                        raise ValueError(
                            "Compliance Lead approval is required for critical or serious findings."
                        )
                clean_lifecycle = "ACCEPTED_RISK"
                clean_action = (remediation_action or "Accepted risk").strip()
                activity_label = "Accepted risk"
            elif clean_action_type == "START_REMEDIATION":
                clean_lifecycle = "IN_PROGRESS"
                clean_action = (remediation_action or "Started remediation").strip()
                activity_label = "Started remediation"
            elif clean_action_type == "MARK_RESOLVED":
                clean_lifecycle = "VERIFIED"
                clean_action = (remediation_action or "Marked as resolved").strip()
                activity_label = "Marked resolved"
            elif clean_action_type == "APPLY_RECOMMENDED_FIX":
                clean_lifecycle = (
                    str(getattr(remediation_status, "value", remediation_status)).strip().upper()
                    if remediation_status
                    else "VERIFIED"
                )
                clean_action = (
                    remediation_action.strip()
                    if remediation_action and remediation_action.strip()
                    else f"Applied recommended fix: {org_fix}"
                )
                activity_label = "Applied recommended fix"
            else:
                clean_lifecycle = (
                    str(getattr(remediation_status, "value", remediation_status)).strip().upper()
                    if remediation_status
                    else "REMEDIATED_PENDING_VERIFICATION"
                )
                clean_action = (remediation_action or "Remediation updated").strip()
                activity_label = clean_action

            parsed_due_date: str | None = None
            if due_date and due_date.strip():
                parsed_due_date = date.fromisoformat(due_date.strip()[:10]).isoformat()

            is_verified = clean_lifecycle == "VERIFIED"
            now_iso = datetime.now(timezone.utc).isoformat()
            frameworks_updated: list[dict[str, Any]] = []

            for target in targets:
                finding_id = target["finding_id"]
                assessment_id = target["assessment_id"]
                fw_code = target["framework_code"]

                effective_assigned_to = clean_assigned_to or target.get("assigned_to")
                existing_due = target.get("due_date")
                effective_due_date = parsed_due_date or (
                    existing_due.isoformat()
                    if isinstance(existing_due, date)
                    else (str(existing_due)[:10] if existing_due else None)
                )
                effective_approved_by = clean_approved_by or target.get("approved_by")

                existing_log = target.get("activity_log") or []
                if isinstance(existing_log, str):
                    existing_log = json.loads(existing_log)
                updated_log = list(existing_log)
                updated_log.append({
                    "action": activity_label,
                    "status": clean_lifecycle,
                    "actor": remediated_by or effective_assigned_to or "User",
                    "assigned_to": effective_assigned_to,
                    "due_date": effective_due_date,
                    "approved_by": effective_approved_by,
                    "note": clean_notes,
                    "timestamp": now_iso,
                })

                remediated_at_val = connection.execute(
                    update_finding_stmt,
                    {
                        "finding_id": finding_id,
                        "remediation_status": clean_lifecycle,
                        "is_remediated": is_verified,
                        "remediation_action": clean_action,
                        "remediated_by": remediated_by or effective_assigned_to,
                        "remediation_notes": clean_notes,
                        "assigned_to": effective_assigned_to,
                        "due_date": effective_due_date,
                        "approved_by": effective_approved_by,
                        "activity_log": json.dumps(updated_log),
                    },
                ).scalar_one()

                sibling_rows = connection.execute(
                    all_findings_stmt,
                    {"assessment_id": assessment_id},
                ).mappings().all()

                effective_evals = [
                    SimpleNamespace(
                        status=(
                            "Good"
                            if (
                                row.get("remediation_status") == "VERIFIED"
                                or (row.get("remediation_status") is None and row["is_remediated"])
                            )
                            else row["status"]
                        )
                    )
                    for row in sibling_rows
                ]
                metrics = calculate_metrics(effective_evals)

                connection.execute(
                    update_assessment_stmt,
                    {
                        "assessment_id": assessment_id,
                        "score": int(round(metrics.score)) if metrics.score is not None else None,
                        "risk_band": str(getattr(metrics.risk_band, "value", metrics.risk_band)),
                        "assessment_status": str(
                            getattr(metrics.assessment_status, "value", metrics.assessment_status)
                        ),
                        "good_count": metrics.good_count,
                        "in_scope_count": metrics.total_in_scope,
                        "critical_count": metrics.critical_count,
                        "serious_count": metrics.serious_count,
                        "needs_review_count": metrics.needs_review_count,
                    },
                )

                frameworks_updated.append({
                    "framework_code": fw_code,
                    "finding_id": finding_id,
                    "original_status": target["original_status"],
                    "remediation_status": clean_lifecycle,
                    "is_remediated": is_verified,
                    "remediation_action": clean_action,
                    "remediated_by": remediated_by or effective_assigned_to,
                    "remediated_at": remediated_at_val.isoformat() if remediated_at_val else None,
                    "assigned_to": effective_assigned_to,
                    "due_date": effective_due_date,
                    "approved_by": effective_approved_by,
                    "updated_metrics": metrics.model_dump(),
                })

            return {
                "discovery_run_id": run_id_str,
                "table_name": clean_table,
                "column_name": clean_col,
                "remediated_findings_count": len(frameworks_updated),
                "frameworks_updated": frameworks_updated,
            }