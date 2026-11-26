from __future__ import annotations

from datetime import datetime
from typing import Any


FRAMEWORK_META: dict[str, dict[str, str]] = {
    "hipaa": {
        "key": "hipaa",
        "name": "HIPAA",
        "fullName": "Health Insurance Portability and Accountability Act",
        "region": "United States · Healthcare",
        "scopeNote": "columns classified as PHI (protected health information)",
    },
    "gdpr": {
        "key": "gdpr",
        "name": "GDPR",
        "fullName": "General Data Protection Regulation",
        "region": "European Union",
        "scopeNote": "columns classified as personal data (PII) or special category data (PHI / Sensitive) under Article 9",
    },
    "dpdp": {
        "key": "dpdp",
        "name": "DPDP",
        "fullName": "Digital Personal Data Protection Act, 2023",
        "region": "India",
        "scopeNote": "columns classified as Personal Data belonging to a Data Principal",
    },
    "ccpa": {
        "key": "ccpa",
        "name": "CCPA/CPRA",
        "fullName": "California Consumer Privacy Act / Privacy Rights Act",
        "region": "California, United States",
        "scopeNote": "columns classified as personal information or sensitive personal information",
    },
}

CLASSIFICATION_KEYS = ("Public", "PII", "PHI", "Financial", "Sensitive")


def _to_dict(item: Any) -> dict[str, Any]:
    if isinstance(item, dict):
        return item
    if hasattr(item, "model_dump"):
        return item.model_dump()
    if hasattr(item, "__dict__"):
        return dict(item.__dict__)
    return {}


def _normalize_classification(raw_val: Any) -> str:
    val = str(raw_val or "PUBLIC").strip().lower()
    mapping = {
        "public": "Public",
        "pii": "PII",
        "phi": "PHI",
        "financial": "Financial",
        "sensitive": "Sensitive",
    }
    return mapping.get(val, "Public")


def _format_timestamps(raw_ts: Any) -> tuple[str | None, str | None]:
    if not raw_ts:
        return None, None
    iso_str = raw_ts.isoformat() if isinstance(raw_ts, datetime) else str(raw_ts)
    try:
        dt = (
            raw_ts
            if isinstance(raw_ts, datetime)
            else datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
        )
        hour_12 = dt.strftime("%I").lstrip("0") or "12"
        label = f"{dt.strftime('%m/%d/%Y')}, {hour_12}:{dt.strftime('%M:%S %p')}"
    except Exception:
        label = iso_str
    return iso_str, label


class ReportGenerationAgent:
    def _build_connection(self, state: dict[str, Any]) -> dict[str, Any]:
        run_info = _to_dict(state.get("run"))
        conn = _to_dict(state.get("connection") or state.get("datasource"))
        _, started_label = _format_timestamps(run_info.get("started_at"))
        _, created_label = _format_timestamps(
            conn.get("created_at") or run_info.get("created_at")
        )

        conn_id = (
            conn.get("connection_id")
            or conn.get("id")
            or run_info.get("connection_id")
            or state.get("connection_id")
        )
        status_raw = str(
            conn.get("discovery_status")
            or conn.get("status")
            or run_info.get("status")
            or ""
        ).lower()
        status = (
            "Discovered"
            if status_raw in {"succeeded", "completed", "discovered", "running"}
            else (conn.get("status") or "Discovered")
        )

        return {
            "id": str(conn_id) if conn_id is not None else "",
            "name": conn.get("connection_name") or conn.get("name") or "",
            "type": str(conn.get("database_type") or conn.get("type") or "").lower(),
            "host": conn.get("host") or "",
            "port": str(conn.get("port") or ""),
            "database": conn.get("database_name") or conn.get("database") or "",
            "username": conn.get("username") or "",
            "ssl": bool(
                conn.get("ssl_enabled")
                if conn.get("ssl_enabled") is not None
                else (conn.get("ssl") or False)
            ),
            "status": status,
            "lastDiscovered": started_label,
            "createdAt": created_label,
        }

    def _build_tables_and_classifications(
        self,
        table_profiles: list[Any],
        column_profiles: list[Any],
        classifications: list[Any],
    ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        cls_lookup: dict[tuple[str, str], dict[str, Any]] = {}
        cls_rows: list[dict[str, Any]] = []
        counts: dict[str, int] = {k: 0 for k in CLASSIFICATION_KEYS}

        for raw_cls in classifications:
            c = _to_dict(raw_cls)
            tbl = str(c.get("table_name") or "")
            col = str(c.get("column_name") or "")
            norm_cls = _normalize_classification(
                c.get("display_classification") or c.get("classification")
            )
            counts[norm_cls] = counts.get(norm_cls, 0) + 1

            samples = c.get("samples") or ([c["sample"]] if c.get("sample") else [])
            sample_val = (
                c.get("sample")
                if c.get("sample") is not None
                else (samples[0] if samples else None)
            )

            if tbl and col:
                cls_lookup[(tbl.lower(), col.lower())] = {
                    "classification": norm_cls,
                    "samples": samples,
                    "sample": sample_val,
                    "confidence": c.get("confidence"),
                    "needs_human_review": bool(c.get("needs_human_review", False)),
                }

            cls_rows.append(
                {
                    "table": tbl,
                    "column": col,
                    "dataType": c.get("data_type") or "",
                    "classification": norm_cls,
                    "confidence": c.get("confidence"),
                    "sample": sample_val,
                }
            )

        col_profiles_by_table: dict[str, list[dict[str, Any]]] = {}
        for raw_cp in column_profiles:
            cp = _to_dict(raw_cp)
            tbl = str(cp.get("table_name") or "").lower()
            if tbl:
                col_profiles_by_table.setdefault(tbl, []).append(cp)

        ui_tables: list[dict[str, Any]] = []
        for raw_tp in table_profiles:
            tp = _to_dict(raw_tp)
            tbl_name = str(tp.get("table_name") or "")
            props = _to_dict(tp.get("properties"))
            dq = _to_dict(tp.get("data_quality_profile"))

            row_count = int(props.get("rows") or 0)
            pk_list = list(props.get("primary_key_columns") or [])
            fk_list = list(props.get("foreign_key_columns") or [])
            pk_cols = {str(x).lower() for x in pk_list}
            fk_lookup = {str(x).lower(): str(x) for x in fk_list}
            pk_col = pk_list[0] if pk_list else None
            avg_null_pct = float(props.get("average_null_rate") or 0.0)
            missing_cells = int(dq.get("missing_cells") or 0)

            raw_cols = tp.get("column_profiles") or col_profiles_by_table.get(
                tbl_name.lower(), []
            )
            total_cells = row_count * len(raw_cols)
            missing_cells_pct = (
                round((missing_cells / total_cells) * 100, 1)
                if total_cells > 0
                else avg_null_pct
            )

            nested_columns: list[dict[str, Any]] = []
            table_alerts: list[dict[str, str]] = []

            for raw_col in raw_cols:
                cp = _to_dict(raw_col)
                col_name = str(cp.get("column_name") or "")
                col_key = col_name.lower()
                cls_info = cls_lookup.get((tbl_name.lower(), col_key), {})
                distinct_cnt = int(cp.get("distinct_count") or 0)
                distinct_pct = (
                    round((distinct_cnt / row_count) * 100, 1)
                    if row_count > 0
                    else 0.0
                )
                is_pk = col_key in pk_cols
                fk_val: str | bool = fk_lookup[col_key] if col_key in fk_lookup else False

                col_alerts: list[str] = []
                if cls_info.get("needs_human_review"):
                    col_alerts.append("Needs human review")
                    table_alerts.append(
                        {"column": col_name, "alert": "Needs human review"}
                    )

                nested_columns.append(
                    {
                        "name": col_name,
                        "type": cp.get("data_type") or "",
                        "pk": is_pk,
                        "fk": fk_val,
                        "classification": cls_info.get("classification") or "Public",
                        "nullPct": avg_null_pct,
                        "missingCount": 0,
                        "distinct": distinct_cnt,
                        "distinctPct": distinct_pct,
                        "samples": cls_info.get("samples") or [],
                        "numeric": (
                            {"mean": cp.get("mean")}
                            if cp.get("mean") is not None
                            else None
                        ),
                        "dateRange": None,
                        "mostFrequent": None,
                        "alerts": col_alerts,
                    }
                )

            complexity_raw = str(props.get("complexity") or "Low").capitalize()
            ui_tables.append(
                {
                    "name": tbl_name,
                    "type": str(tp.get("object_type") or "TABLE").lower(),
                    "rowCount": row_count,
                    "columnCount": int(props.get("columns") or len(nested_columns)),
                    "avgNullPct": avg_null_pct,
                    "columns": nested_columns,
                    "fkCount": len(fk_list),
                    "pkColumn": pk_col,
                    "complexity": complexity_raw,
                    "numericCount": int(dq.get("numeric_column_count") or 0),
                    "categoricalCount": int(dq.get("categorical_column_count") or 0),
                    "missingCellsPct": missing_cells_pct,
                    "duplicateRowsPct": float(
                        dq.get("duplicate_row_percentage") or 0.0
                    ),
                    "memoryBytes": int(dq.get("memory_size_bytes") or 0),
                    "alerts": table_alerts,
                }
            )

        return ui_tables, {"rows": cls_rows, "counts": counts}

    def _build_objects(
        self, objects: list[Any], dependencies: list[Any]
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
            elif any(
                token in rel for token in ("WRITE", "INSERT", "UPDATE", "DELETE")
            ):
                writes_map.setdefault(src.lower(), []).append(tgt)

        non_table_types = {
            "VIEW",
            "MATERIALIZED_VIEW",
            "PROCEDURE",
            "STORED_PROCEDURE",
            "FUNCTION",
            "TRIGGER",
        }
        result_objects: list[dict[str, Any]] = []

        for raw_obj in objects:
            obj = _to_dict(raw_obj)
            obj_type = str(obj.get("object_type") or "").upper()
            if obj_type not in non_table_types:
                continue

            schema_name = str(obj.get("schema_name") or "")
            obj_name = str(obj.get("object_name") or "")
            fqn = f"{schema_name}.{obj_name}" if schema_name else obj_name

            reads: list[str] = []
            writes: list[str] = []
            for key in (obj_name.lower(), fqn.lower()):
                for r in reads_map.get(key, []):
                    if r not in reads:
                        reads.append(r)
                for w in writes_map.get(key, []):
                    if w not in writes:
                        writes.append(w)

            definition = obj.get("definition") or obj.get("sql_definition") or ""
            raw_loc = len(str(definition).splitlines()) if definition else 0
            extra_meta = obj.get("metadata") or obj.get("properties") or {}
            extra_dict = extra_meta if isinstance(extra_meta, dict) else {}

            lines_of_code = (
                raw_loc
                if raw_loc > 0
                else int(
                    extra_dict.get("lines_of_code")
                    or extra_dict.get("linesOfCode")
                    or 0
                )
            )

            raw_params = (
                obj.get("parameters")
                if obj.get("parameters") is not None
                else obj.get("params")
            )
            if raw_params is None or raw_params == 0:
                params_val = int(
                    extra_dict.get("parameter_count")
                    or extra_dict.get("params")
                    or 0
                )
            else:
                params_val = raw_params

            language_val = obj.get("language") or extra_dict.get("language") or "SQL"
            if str(language_val).lower() == "sql":
                language_val = "SQL"

            updated = obj.get("last_altered") or obj.get("updated_at")
            last_altered = (
                updated.isoformat()
                if isinstance(updated, datetime)
                else (str(updated) if updated else None)
            )

            result_objects.append(
                {
                    "name": obj_name,
                    "type": obj_type.lower(),
                    "reads": reads,
                    "writes": writes,
                    "params": params_val,
                    "language": language_val,
                    "linesOfCode": lines_of_code,
                    "lastAltered": last_altered,
                    "extra": extra_dict,
                    "complexity": "Low",
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
            props = _to_dict(tp.get("properties"))
            rows = int(props.get("rows") or 0)
            for key in (
                tp.get("table_name"),
                f"{tp.get('schema_name')}.{tp.get('table_name')}",
            ):
                if key:
                    row_count_by_name[str(key).lower()] = rows

        nodes: list[dict[str, Any]] = []
        seen_ids: set[str] = set()

        for raw_obj in objects:
            obj = _to_dict(raw_obj)
            schema_name = str(obj.get("schema_name") or "")
            obj_name = str(obj.get("object_name") or "")
            fqn = f"{schema_name}.{obj_name}" if schema_name else obj_name
            node_id = obj_name or fqn or str(obj.get("object_id") or "")
            if not node_id or node_id in seen_ids:
                continue
            seen_ids.add(node_id)
            obj_type = str(obj.get("object_type") or "OBJECT").lower()
            node: dict[str, Any] = {
                "id": node_id,
                "type": obj_type,
            }
            if obj_type == "table":
                node["rowCount"] = row_count_by_name.get(
                    fqn.lower(), row_count_by_name.get(obj_name.lower(), 0)
                )
            nodes.append(node)

        edges: list[dict[str, Any]] = []
        for raw_dep in dependencies:
            dep = _to_dict(raw_dep)
            src = str(dep.get("source_object") or "")
            tgt = str(dep.get("target_object") or "")
            rel = str(dep.get("relationship_type") or "").upper()
            src_col = dep.get("source_column") or dep.get("from_column")
            tgt_col = dep.get("target_column") or dep.get("to_column")

            if "FOREIGN" in rel or rel == "FK":
                kind = "FK"
                label = (
                    f"{src_col} -> {tgt}.{tgt_col}"
                    if (src_col and tgt_col)
                    else f"{src} -> {tgt}"
                )
            elif "READ" in rel:
                kind = "READS"
                label = "reads"
            elif "WRITE" in rel:
                kind = "WRITES"
                label = "writes"
            else:
                kind = rel or "DEPENDENCY"
                label = f"{src} -> {tgt}" if (src and tgt) else rel

            edges.append(
                {
                    "from": src,
                    "to": tgt,
                    "label": label,
                    "kind": kind,
                }
            )

        return {"nodes": nodes, "edges": edges}

    def _build_compliance(self, compliance_results: Any) -> dict[str, Any]:
        if not compliance_results:
            return {}
        items = (
            compliance_results
            if isinstance(compliance_results, list)
            else [compliance_results]
        )
        compliance_map: dict[str, Any] = {}

        for raw_res in items:
            res = _to_dict(raw_res)
            fw_raw = str(
                res.get("framework_code")
                or res.get("framework")
                or res.get("key")
                or "general"
            ).lower()
            meta = FRAMEWORK_META.get(
                fw_raw,
                {
                    "key": fw_raw,
                    "name": fw_raw.upper(),
                    "fullName": str(res.get("framework_name") or fw_raw.upper()),
                    "region": "",
                    "scopeNote": "",
                },
            )
            raw_findings = res.get("findings") or []
            findings: list[dict[str, Any]] = []
            sev_counts = {"good": 0, "warning": 0, "serious": 0, "critical": 0}

            for raw_f in raw_findings:
                f = _to_dict(raw_f)
                status = str(f.get("status") or "warning").lower()
                if status in sev_counts:
                    sev_counts[status] += 1
                findings.append(
                    {
                        "table": f.get("table_name") or f.get("table") or "",
                        "column": f.get("column_name") or f.get("column") or "",
                        "classification": f.get("classification") or "PHI",
                        "status": status,
                        "issue": f.get("finding_text") or f.get("issue") or "",
                        "rec": f.get("recommendation_text") or f.get("rec") or "",
                    }
                )

            score = (
                res.get("compliance_score")
                if res.get("compliance_score") is not None
                else res.get("score")
            )
            band = res.get("risk_band") or res.get("band") or "serious"
            counts = {
                "good": int(
                    res.get("good_count")
                    if res.get("good_count") is not None
                    else sev_counts["good"]
                ),
                "warning": sev_counts["warning"],
                "serious": int(
                    res.get("serious_count")
                    if res.get("serious_count") is not None
                    else sev_counts["serious"]
                ),
                "critical": int(
                    res.get("critical_count")
                    if res.get("critical_count") is not None
                    else sev_counts["critical"]
                ),
            }

            compliance_map[fw_raw] = {
                "key": meta["key"],
                "name": meta["name"],
                "fullName": meta["fullName"],
                "region": meta["region"],
                "scopeNote": meta["scopeNote"],
                "findings": findings,
                "score": score,
                "band": band,
                "counts": counts,
            }

        return compliance_map

    def build(self, state: dict[str, Any]) -> dict[str, Any]:
        run_info = _to_dict(state.get("run"))
        overview = _to_dict(state.get("overview"))
        objects = state.get("objects") or []
        classifications = state.get("classifications") or []
        dependencies = state.get("dependencies") or []
        table_profiles = state.get("table_profiles") or []
        column_profiles = state.get("column_profiles") or []
        compliance_results = state.get("compliance_results")

        scopes = [
            str(s).upper()
            for s in (
                run_info.get("effective_scopes")
                or run_info.get("requested_scopes")
                or []
            )
        ]
        has_cls = "COLUMN_CLASSIFICATION" in scopes or bool(classifications)
        has_dep = "DEPENDENCY_MAP" in scopes or bool(dependencies)
        has_cmp = "REGULATORY_COMPLIANCE" in scopes or bool(compliance_results)

        tables, cls_section = self._build_tables_and_classifications(
            table_profiles=table_profiles,
            column_profiles=column_profiles,
            classifications=classifications,
        )
        non_table_objects = self._build_objects(
            objects=objects, dependencies=dependencies
        )
        dependency_graph = self._build_dependency_graph(
            objects=objects,
            table_profiles=table_profiles,
            dependencies=dependencies,
        )
        compliance_section = self._build_compliance(
            compliance_results=compliance_results
        )

        started_iso, started_label = _format_timestamps(run_info.get("started_at"))
        generated_iso, generated_label = _format_timestamps(
            run_info.get("completed_at")
            or run_info.get("updated_at")
            or run_info.get("started_at")
        )
        selected_objs = run_info.get("selected_objects") or []
        db_size_bytes = overview.get("estimated_database_size_bytes")
        if db_size_bytes is None:
            db_size_bytes = sum(int(t.get("memoryBytes") or 0) for t in tables)

        run_id = str(
            run_info.get("discovery_run_id") or state.get("discovery_run_id") or ""
        )

        return {
            "connection": self._build_connection(state),
            "run": {
                "id": run_id,
                "startedAt": started_iso,
                "startedAtLabel": started_label,
                "options": {
                    "classification": has_cls,
                    "dependency": has_dep,
                    "compliance": has_cmp,
                },
                "results": {
                    "generatedAt": generated_label or generated_iso,
                    "tables": tables,
                    "objects": non_table_objects,
                    "objectScope": {
                        "selectedCount": (
                            len(selected_objs) if selected_objs else len(objects)
                        ),
                        "totalCount": (
                            len(objects) if objects else len(selected_objs)
                        ),
                    },
                    "dbSizeBytes": db_size_bytes,
                    "dateRange": None,
                    "classification": cls_section,
                    "dependency": dependency_graph,
                    "compliance": compliance_section,
                    "shownTabs": {
                        "classification": has_cls,
                        "dependency": has_dep,
                        "compliance": has_cmp,
                    },
                },
            },
        }