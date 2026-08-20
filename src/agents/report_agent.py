class ReportGenerationAgent:
    def build(self, state: dict) -> dict:
        classifications = state.get("classifications", [])
        findings = state.get("hipaa_findings", [])
        return {
            "discovery_run_id": state["discovery_run_id"],
            "overview": {
                "tables": len(state.get("table_profiles", [])),
                "columns": len(state.get("column_profiles", [])),
                "classifications": len(classifications),
                "dependencies": len(state.get("dependencies", [])),
                "hipaa_findings": len(findings),
            },
            "table_profiles": state.get("table_profiles", []),
            "classifications": [x.model_dump() if hasattr(x, "model_dump") else x for x in classifications],
            "dependencies": [x.model_dump() if hasattr(x, "model_dump") else x for x in state.get("dependencies", [])],
            "hipaa_findings": [x.model_dump() if hasattr(x, "model_dump") else x for x in findings],
            "hipaa_score": state.get("hipaa_score").model_dump() if state.get("hipaa_score") else None,
        }
