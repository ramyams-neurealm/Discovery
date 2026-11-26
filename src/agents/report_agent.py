from __future__ import annotations

from typing import Any


def _to_dict(item: Any) -> dict[str, Any]:
    if isinstance(item, dict):
        return item
    if hasattr(item, "model_dump"):
        return item.model_dump()
    if hasattr(item, "__dict__"):
        return dict(item.__dict__)
    return {}


class ReportGenerationAgent:
    def _build_vertical_tables(
        self,
        table_profiles: list[Any],
        column_profiles: list[Any],
        classifications: list[Any],
    ) -> list[dict[str, Any]]:
        cls_lookup: dict[tuple[str, str], dict[str, Any]] = {}
        for raw_cls in classifications:
            c = _to_dict(raw_cls)
            tbl = str(c.get("table_name") or "").lower()
            col = str(c.get("column_name") or "").lower()
            if tbl and col:
                cls_lookup[(tbl, col)] = c

        col_profiles_by_table: dict[str, list[dict[str, Any]]] = {}
        for raw_cp in column_profiles:
            cp = _to_dict(raw_cp)
            tbl = str(cp.get("table_name") or "").lower()
            if tbl:
                col_profiles_by_table.setdefault(tbl, []).append(cp)

        vertical_tables: list[dict[str, Any]] = []
        for raw_tp in table_profiles:
            tp = _to_dict(raw_tp)
            tbl_name = str(tp.get("table_name") or "")
            props = tp.get("properties") or {}
            dq = tp.get("data_quality_profile") or {}
            pk_cols = set(str(x).lower() for x in (props.get("primary_key_columns") or []))
            fk_cols = set(str(x).lower() for x in (props.get("foreign_key_columns") or []))

            raw_cols = tp.get("column_profiles") or col_profiles_by_table.get(tbl_name.lower(), [])
            nested_columns: list[dict[str, Any]] = []
            for raw_col in raw_cols:
                cp = _to_dict(raw_col)
                col_name = str(cp.get("column_name") or "")
                cls_info = cls_lookup.get((tbl_name.lower(), col_name.lower()), {})
                nested_columns.append(
                    {
                        "name": col_name,
                        "type": cp.get("data_type"),
                        "pk": col_name.lower() in pk_cols,
                        "fk": col_name.lower() in fk_cols,
                        "classification": cls_info.get("display_classification"),
                        "sensitiveDataType": cls_info.get("sensitive_data_type"),
                        "confidence": cls_info.get("confidence"),
                        "reason": cls_info.get("reason"),
                        "needsHumanReview": cls_info.get("needs_human_review"),
                        "distinctCount": cp.get("distinct_count"),
                        "numeric": {
                            "mean": cp.get("mean"),
                        }
                        if cp.get("mean") is not None
                        else None,
                        "samples": cls_info.get("samples") or ([cls_info["sample"]] if cls_info.get("sample") else []),
                    }
                )

            vertical_tables.append(
                {
                    "id": tp.get("object_id"),
                    "schema": tp.get("schema_name"),
                    "name": tbl_name,
                    "type": str(tp.get("object_type") or "TABLE").lower(),
                    "rowCount": props.get("rows", 0),
                    "columnCount": props.get("columns", len(nested_columns)),
                    "avgNullPct": props.get("average_null_rate", 0.0),
                    "complexity": props.get("complexity"),
                    "pkColumns": list(props.get("primary_key_columns") or []),
                    "fkColumns": list(props.get("foreign_key_columns") or []),
                    "numericCount": dq.get("numeric_column_count", 0),
                    "categoricalCount": dq.get("categorical_column_count", 0),
                    "otherColumnCount": dq.get("other_column_count", 0),
                    "missingCells": dq.get("missing_cells", 0),
                    "duplicateRows": dq.get("duplicate_row_count", 0),
                    "duplicateRowsPct": dq.get("duplicate_row_percentage", 0.0),
                    "memoryBytes": dq.get("memory_size_bytes", 0),
                    "memoryMb": dq.get("memory_size_mb", 0.0),
                    "columns": nested_columns,
                }
            )

        return vertical_tables

    def _build_non_table_objects(
        self,
        objects: list[Any],
        dependencies: list[Any],
    ) -> list[dict[str, Any]]:
        reads_map: dict[str, list[str]] = {}
        writes_map: dict[str, list[str]] = {}

        for raw_dep in dependencies:
            dep = _to_dict(raw_dep)
            src = str(dep.get("source_object") or "")
            tgt = str(dep.get("target_object") or "")
            rel = str(dep.get("relationship_type") or "").upper()
            if not src or not tgt:
                continue
            if "READ" in rel:
                reads_map.setdefault(src.lower(), []).append(tgt)
            elif "WRITE" in rel or "INSERT" in rel or "UPDATE" in rel or "DELETE" in rel:
                writes_map.setdefault(src.lower(), []).append(tgt)

        non_table_types = {"VIEW", "MATERIALIZED_VIEW", "PROCEDURE", "STORED_PROCEDURE", "FUNCTION", "TRIGGER"}
        result_objects: list[dict[str, Any]] = []

        for raw_obj in objects:
            obj = _to_dict(raw_obj)
            obj_type = str(obj.get("object_type") or "").upper()
            if obj_type not in non_table_types:
                continue

            schema_name = str(obj.get("schema_name") or "")
            obj_name = str(obj.get("object_name") or "")
            fqn = f"{schema_name}.{obj_name}" if schema_name else obj_name
            lookup_keys = [obj_name.lower(), fqn.lower()]

            reads: list[str] = []
            writes: list[str] = []
            for k in lookup_keys:
                for r in reads_map.get(k, []):
                    if r not in reads:
                        reads.append(r)
                for w in writes_map.get(k, []):
                    if w not in writes:
                        writes.append(w)

            definition = obj.get("definition") or obj.get("sql_definition") or ""
            loc = len(str(definition).splitlines()) if definition else 0
            extra_meta = obj.get("metadata") or obj.get("properties") or {}

            result_objects.append(
                {
                    "id": obj.get("object_id") or fqn,
                    "schema": schema_name,
                    "name": obj_name,
                    "type": obj_type.lower(),
                    "reads": reads,
                    "writes": writes,
                    "params": obj.get("parameters") or obj.get("params") or [],
                    "language": obj.get("language") or "sql",
                    "linesOfCode": loc,
                    "lastAltered": obj.get("last_altered") or obj.get("updated_at"),
                    "extra": extra_meta if isinstance(extra_meta, dict) else {},
                }
            )

        return result_objects

    def _build_dependency_graph(
        self,
        objects: list[Any],
        table_profiles: list[Any],
        dependencies: list[Any],
    ) -> dict[str, list[dict[str, Any]]]:
        row_count_by_name: dict[str, int] = {}
        for raw_tp in table_profiles:
            tp = _to_dict(raw_tp)
            props = tp.get("properties") or {}
            rows = props.get("rows", 0)
            for key in (tp.get("table_name"), f"{tp.get('schema_name')}.{tp.get('table_name')}"):
                if key:
                    row_count_by_name[str(key).lower()] = rows

        nodes: list[dict[str, Any]] = []
        seen_node_ids: set[str] = set()

        for raw_obj in objects:
            obj = _to_dict(raw_obj)
            schema_name = str(obj.get("schema_name") or "")
            obj_name = str(obj.get("object_name") or "")
            fqn = f"{schema_name}.{obj_name}" if schema_name else obj_name
            node_id = str(obj.get("object_id") or fqn)
            if not node_id or node_id in seen_node_ids:
                continue
            seen_node_ids.add(node_id)
            obj_type = str(obj.get("object_type") or "OBJECT").lower()
            nodes.append(
                {
                    "id": node_id,
                    "name": obj_name,
                    "schema": schema_name,
                    "type": obj_type,
                    "rowCount": row_count_by_name.get(fqn.lower(), row_count_by_name.get(obj_name.lower(), 0)),
                }
            )

        edges: list[dict[str, Any]] = []
        for raw_dep in dependencies:
            dep = _to_dict(raw_dep)
            src = str(dep.get("source_object") or "")
            tgt = str(dep.get("target_object") or "")
            rel = str(dep.get("relationship_type") or "")
            src_col = dep.get("source_column") or dep.get("from_column")
            tgt_col = dep.get("target_column") or dep.get("to_column")

            if src_col and tgt_col:
                label = f"{src_col} -> {tgt}.{tgt_col}"
            elif src_col:
                label = f"{src_col} -> {tgt}"
            elif src and tgt:
                label = f"{src} -> {tgt}" if not rel else f"{src} -> {tgt} ({rel})"
            else:
                label = rel

            edge_item = dict(dep)
            edge_item["label"] = label
            edges.append(edge_item)

        return {"nodes": nodes, "edges": edges}

    def _build_compliance(self, compliance_results: list[Any], hipaa_findings: list[Any]) -> dict[str, Any]:
        compliance_map: dict[str, Any] = {}
        for raw_res in compliance_results:
            res = _to_dict(raw_res)
            fw = str(res.get("framework") or res.get("framework_code") or "general").lower()
            findings = [_to_dict(f) for f in (res.get("findings") or [])]
            compliance_map[fw] = {
                "score": res.get("score"),
                "band": res.get("band"),
                "counts": res.get("counts") or {"findings": len(findings)},
                "findings": findings,
            }

        if "hipaa" not in compliance_map and hipaa_findings:
            parsed_findings = [_to_dict(f) for f in hipaa_findings]
            compliance_map["hipaa"] = {
                "score": None,
                "band": None,
                "counts": {"findings": len(parsed_findings)},
                "findings": parsed_findings,
            }

        return compliance_map

    def _build_connection(self, state: dict[str, Any]) -> dict[str, Any] | None:
        raw_conn = state.get("connection") or state.get("datasource")
        if not raw_conn:
            return None
        conn = _to_dict(raw_conn)
        return {
            "id": conn.get("connection_id") or conn.get("id") or state.get("connection_id"),
            "name": conn.get("name") or conn.get("connection_name"),
            "type": conn.get("db_type") or conn.get("type") or conn.get("engine"),
            "host": conn.get("host"),
            "port": conn.get("port"),
            "database": conn.get("database") or conn.get("database_name"),
            "schema": conn.get("schema") or conn.get("schema_name"),
            "username": conn.get("username"),
            "ssl": conn.get("ssl"),
            "status": conn.get("status"),
        }

    def build(self, state: dict[str, Any]) -> dict[str, Any]:
        objects = state.get("objects", [])
        classifications = state.get("classifications", [])
        dependencies = state.get("dependencies", [])
        table_profiles = state.get("table_profiles", [])
        column_profiles = state.get("column_profiles", [])
        compliance_results = state.get("compliance_results", [])
        hipaa_findings = state.get("hipaa_findings", [])

        vertical_tables = self._build_vertical_tables(
            table_profiles=table_profiles,
            column_profiles=column_profiles,
            classifications=classifications,
        )
        non_table_objects = self._build_non_table_objects(
            objects=objects,
            dependencies=dependencies,
        )
        dependency_graph = self._build_dependency_graph(
            objects=objects,
            table_profiles=table_profiles,
            dependencies=dependencies,
        )
        compliance_section = self._build_compliance(
            compliance_results=compliance_results,
            hipaa_findings=hipaa_findings,
        )

        total_findings = sum(
            len(item.get("findings") or [])
            for item in compliance_section.values()
            if isinstance(item, dict)
        )

        return {
            "discovery_run_id": state.get("discovery_run_id"),
            "connection": self._build_connection(state),
            "run": {
                "id": state.get("discovery_run_id"),
                "connectionId": state.get("connection_id"),
                "status": state.get("status"),
                "scopes": state.get("effective_scopes") or state.get("requested_scopes") or [],
                "selectedObjects": state.get("selected_objects") or [],
                "selectedFrameworks": state.get("selected_frameworks") or [],
            },
            "results": {
                "tables": vertical_tables,
                "objects": non_table_objects,
                "dependency": dependency_graph,
                "compliance": compliance_section,
            },
            "overview": {
                "tables": len(vertical_tables),
                "objects": len(non_table_objects),
                "columns": len(column_profiles),
                "classifications": len(classifications),
                "dependencies": len(dependencies),
                "compliance_frameworks_assessed": len(compliance_section),
                "compliance_findings_count": total_findings,
            },
        }
