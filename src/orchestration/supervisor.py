from uuid import uuid4
from langgraph.graph import END, START, StateGraph
from src.agents.metadata_profiling_agent import MetadataDiscoveryProfilingAgent
from src.agents.classification_agent import DataClassificationAgent
from src.agents.dependency_mapping_agent import DependencyMappingAgent
from src.agents.hipaa_compliance_score_agent import HipaaComplianceScoreAgent
from src.agents.report_agent import ReportGenerationAgent
from src.orchestration.state import DiscoveryState


class DiscoverySupervisor:
    def __init__(self, metadata_agent, classification_agent, dependency_agent, hipaa_agent, report_agent):
        self.metadata_agent = metadata_agent
        self.classification_agent = classification_agent
        self.dependency_agent = dependency_agent
        self.hipaa_agent = hipaa_agent
        self.report_agent = report_agent
        self.graph = self._build_graph()

    def _metadata(self, state: DiscoveryState) -> DiscoveryState:
        out = self.metadata_agent.run(state["discovery_run_id"], state["source_connection"])
        return {**state, **out, "status": "RUNNING"}

    def _classify(self, state: DiscoveryState) -> DiscoveryState:
        if "COLUMN_CLASSIFICATION" not in state["effective_scopes"]:
            return state
        results = [self.classification_agent.classify(row) for row in state.get("column_profiles", [])]
        return {**state, "classifications": results}

    def _dependencies(self, state: DiscoveryState) -> DiscoveryState:
        if "DEPENDENCY_MAP" not in state["effective_scopes"]:
            return state
        return {**state, "dependencies": self.dependency_agent.run(state.get("objects", []))}

    def _hipaa(self, state: DiscoveryState) -> DiscoveryState:
        if "HIPAA_COMPLIANCE" not in state["effective_scopes"]:
            return state
        findings, score = self.hipaa_agent.evaluate(state.get("classifications", []))
        return {**state, "hipaa_findings": findings, "hipaa_score": score}

    def _report(self, state: DiscoveryState) -> DiscoveryState:
        report = self.report_agent.build(state)
        return {**state, "report": report, "status": "SUCCEEDED"}

    def _build_graph(self):
        graph = StateGraph(DiscoveryState)
        graph.add_node("metadata_and_profiling", self._metadata)
        graph.add_node("classification", self._classify)
        graph.add_node("dependency_mapping", self._dependencies)
        graph.add_node("hipaa", self._hipaa)
        graph.add_node("report", self._report)
        graph.add_edge(START, "metadata_and_profiling")
        # Reference implementation is sequential for simplicity. Replace these edges
        # with LangGraph fan-out/fan-in once persistence and retries are implemented.
        graph.add_edge("metadata_and_profiling", "classification")
        graph.add_edge("classification", "dependency_mapping")
        graph.add_edge("dependency_mapping", "hipaa")
        graph.add_edge("hipaa", "report")
        graph.add_edge("report", END)
        return graph.compile()

    def invoke(self, connection_id: int, scopes: list[str], source_connection) -> DiscoveryState:
        effective = set(scopes)
        if "HIPAA_COMPLIANCE" in effective:
            effective.add("COLUMN_CLASSIFICATION")
        initial: DiscoveryState = {
            "discovery_run_id": str(uuid4()),
            "connection_id": connection_id,
            "requested_scopes": scopes,
            "effective_scopes": sorted(effective),
            "source_connection": source_connection,
            "errors": [],
            "status": "PENDING",
        }
        return self.graph.invoke(initial)
