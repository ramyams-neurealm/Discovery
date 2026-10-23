from __future__ import annotations

from typing import Any


class ReportGenerationAgent:
    def build(self, state: dict[str, Any]) -> dict[str, Any]:
        classifications = state.get("classifications", [])
        dependencies = state.get("dependencies", [])
        table_profiles = state.get("table_profiles", [])
        column_profiles = state.get("column_profiles", [])
        compliance_results = state.get("compliance_results", [])

        # Count total statutory findings across all evaluated frameworks
        total_findings = sum(
            len(getattr(res, "findings", [])) if hasattr(res, "findings") 
            else len(res.get("findings", [])) if isinstance(res, dict)
            else 0
            for res in compliance_results
        )

        return {
            "discovery_run_id": state["discovery_run_id"],
            "overview": {
                "tables": len(table_profiles),
                "columns": len(column_profiles),
                "classifications": len(classifications),
                "dependencies": len(dependencies),
                "compliance_frameworks_assessed": len(compliance_results),
                "compliance_findings_count": total_findings,
            },
            "table_profiles": table_profiles,
            "classifications": [
                x.model_dump() if hasattr(x, "model_dump") else x 
                for x in classifications
            ],
            "dependencies": [
                x.model_dump() if hasattr(x, "model_dump") else x 
                for x in dependencies
            ],
            "compliance_results": [
                x.model_dump() if hasattr(x, "model_dump") else x 
                for x in compliance_results
            ],
        }