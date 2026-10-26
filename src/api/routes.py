from __future__ import annotations

import asyncio
import logging
from typing import Any
from uuid import UUID, uuid4

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    HTTPException,
    Path,
    Query,
    Response,
    status,
)
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError

from src.api.dependencies import get_database
from src.jobs.discovery_runner import run_discovery_background
from src.models.enums import DatabaseType
from src.models.schemas import (
    ComplianceFrameworkListResponse,
    ControlEvidenceInput,
    ConnectionInput,
    ConnectionUpdate,
    DiscoveryRunRequest,
    DiscoveryRunOverviewResponse,
    PaginatedClassificationsResponse,
    FocusedLineageItem,
    FocusedLineageResponse,
    FullLineageResponse,
    LineageEdge,
    LineageNode,
)
from src.repositories.discovery_repository import DiscoveryRepository
from src.services.database import MetadataDatabase
from src.tools.connection_tools import (
    list_source_objects,
    test_connection,
)
from src.utils.config import Settings, get_settings


logger = logging.getLogger(__name__)
router = APIRouter()
SUPPORTED_FRAMEWORKS = {
    "HIPAA",
    "GDPR",
    "PCI_DSS",
    "GLBA",
    "DPDP",
    "CCPA_CPRA",
    "CCPA",
    "PIPEDA",
}


def _safe_config(
    request: ConnectionInput,
) -> dict[str, Any]:
    """Build the non-secret source-database configuration."""

    config: dict[str, Any] = {
        "host": request.host,
        "port": request.port,
        "database_name": request.database_name,
        "username": request.username,
        "ssl_enabled": request.ssl_enabled,
    }

    if request.schema_name:
        config["schema_name"] = request.schema_name

    return config


def _effective_scopes(requested_scopes: list[str]) -> list[str]:
    """Add internal workflow dependencies required for execution."""
    effective_scopes = set(requested_scopes)

    if (
        "HIPAA_COMPLIANCE" in effective_scopes
        or "REGULATORY_COMPLIANCE" in effective_scopes
    ):
        effective_scopes.add("COLUMN_CLASSIFICATION")

    return sorted(effective_scopes)


def _get_repository(database: MetadataDatabase) -> DiscoveryRepository:
    return DiscoveryRepository(database)


def _lineage_node(
    record: dict[str, Any],
) -> LineageNode:
    schema_name = str(
        record.get("schema_name") or ""
    ).strip()

    object_name = str(
        record.get("object_name") or ""
    ).strip()

    qualified_name = (
        f"{schema_name}.{object_name}"
        if schema_name
        else object_name
    )

    return LineageNode(
        id=str(record["object_id"]),
        schema_name=schema_name,
        object_name=object_name,
        qualified_name=qualified_name,
        type=str(
            record.get("object_type")
            or "unknown"
        ).lower(),
        row_count=(
            int(record["row_count"])
            if record.get("row_count")
            is not None
            else None
        ),
        language=record.get("language"),
    )

def _lineage_edge_values(edge: dict[str, Any]) -> dict[str, str]:
    relationship = str(edge.get("relationship_type") or "DEPENDENCY").upper()
    kind = "FK" if relationship == "FOREIGN_KEY" else relationship
    source_column = edge.get("source_column")
    target_column = edge.get("target_column")
    if source_column and target_column:
        label = f"{source_column} -> {edge['target_object']}.{target_column}"
    else:
        label = relationship
    return {
        "kind": kind,
        "label": label,
    }


def _require_discovery_run(
    repository: DiscoveryRepository,
    run_id: UUID,
) -> dict[str, Any]:
    record = repository.get_run(run_id)

    if record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error_code": "DISCOVERY_RUN_NOT_FOUND",
                "message": "Discovery run not found.",
            },
        )

    return record


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get(
    "/compliance-frameworks",
    response_model=ComplianceFrameworkListResponse,
)
def list_compliance_frameworks(
    database: MetadataDatabase = Depends(get_database),
) -> dict[str, Any]:
    frameworks = _get_repository(database).list_compliance_frameworks()
    return {"framework_count": len(frameworks), "frameworks": frameworks}


@router.post("/connections/test")
def test_database_connection(request: ConnectionInput) -> dict[str, Any]:
    result = test_connection(
        database_type=request.database_type,
        safe_config=_safe_config(request),
        password=request.password.get_secret_value(),
    )

    if not result.success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "status": "FAILED",
                "error_code": getattr(result, "error_code", None)
                or "CONNECTION_TEST_FAILED",
                "message": result.message,
            },
        )

    return {
        "status": "SUCCESS",
        "message": result.message,
        "database_type": request.database_type.value,
        "schema_name": request.schema_name,
        "response_time_ms": result.response_time_ms,
    }


@router.post("/connections", status_code=status.HTTP_201_CREATED)
def create_database_connection(
    request: ConnectionInput,
    database: MetadataDatabase = Depends(get_database),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    test_result = test_connection(
        database_type=request.database_type,
        safe_config=_safe_config(request),
        password=request.password.get_secret_value(),
    )

    if not test_result.success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error_code": "CONNECTION_TEST_FAILED",
                "message": (
                    "Datasource was not saved because the connection test failed."
                ),
                "connection_message": test_result.message,
            },
        )

    repository = _get_repository(database)

    try:
        saved = repository.create_datasource_connection(
            connection_name=request.connection_name,
            database_type=request.database_type.value,
            host=request.host,
            port=request.port,
            database_name=request.database_name,
            schema_name=request.schema_name,
            username=request.username,
            password=request.password.get_secret_value(),
            encryption_key=(
                settings.source_credential_encryption_key.get_secret_value()
            ),
            ssl_enabled=request.ssl_enabled,
        )
    except IntegrityError as error:
        logger.exception("Datasource connection persistence conflict")
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "error_code": "CONNECTION_NAME_EXISTS",
                "message": "A datasource connection with this name already exists.",
            },
        ) from error
    except Exception as error:
        original_error = getattr(error, "orig", error)
        logger.exception("Datasource connection persistence failed")
        detail: dict[str, Any] = {
            "error_code": "CONNECTION_SAVE_FAILED",
            "message": "The datasource connection could not be saved.",
            "failure_type": error.__class__.__name__,
        }
        if settings.app_env in {"local", "development"}:
            detail["database_error"] = str(original_error)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=detail,
        ) from error

    return {
        **saved,
        "connection_test": {
            "status": "SUCCESS",
            "response_time_ms": test_result.response_time_ms,
        },
    }


@router.get("/connections")
def list_database_connections(
    database: MetadataDatabase = Depends(get_database),
) -> list[dict[str, Any]]:
    repository = _get_repository(database)
    records = repository.list_datasource_connections()

    for record in records:
        record.pop("credential_reference", None)
        record.pop("password_encrypted", None)

    return records


@router.get("/connections/{connection_id}")
def get_database_connection(
    connection_id: int,
    database: MetadataDatabase = Depends(get_database),
) -> dict[str, Any]:
    repository = _get_repository(database)
    record = repository.get_datasource_connection(connection_id)

    if record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error_code": "CONNECTION_NOT_FOUND",
                "message": "Datasource connection not found.",
            },
        )

    record.pop("credential_reference", None)
    record.pop("password_encrypted", None)
    return record




@router.get("/connections/{connection_id}/objects")
def list_connection_objects(
    connection_id: int,
    database: MetadataDatabase = Depends(get_database),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    """Return lightweight selectable objects from one datasource."""
    repository = _get_repository(database)
    datasource = repository.get_datasource_connection(connection_id)
    if datasource is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error_code": "CONNECTION_NOT_FOUND",
                "message": "Datasource connection not found.",
            },
        )
    if not datasource.get("is_active", False):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error_code": "CONNECTION_INACTIVE",
                "message": "Datasource connection is inactive.",
            },
        )
    try:
        password = repository.get_datasource_password(
            connection_id=connection_id,
            encryption_key=(
                settings.source_credential_encryption_key.get_secret_value()
            ),
        )
        if not password:
            raise ValueError("Datasource password is unavailable")
        safe_config = {
            "host": datasource["host"],
            "port": datasource["port"],
            "database_name": datasource["database_name"],
            "username": datasource["username"],
            "ssl_enabled": datasource["ssl_enabled"],
        }
        if datasource.get("schema_name"):
            safe_config["schema_name"] = datasource["schema_name"]
        objects = list_source_objects(
            database_type=DatabaseType(datasource["database_type"]),
            safe_config=safe_config,
            password=password,
        )
    except Exception as error:
        logger.exception("Datasource object listing failed")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={
                "error_code": "OBJECT_LISTING_FAILED",
                "message": "Selectable datasource objects could not be listed.",
                "failure_type": error.__class__.__name__,
            },
        ) from error
    finally:
        password = None
    return {
        "connection_id": connection_id,
        "schema_name": datasource.get("schema_name"),
        "object_count": len(objects),
        "objects": objects,
    }

@router.put("/connections/{connection_id}")
def update_database_connection(
    connection_id: int,
    request: ConnectionUpdate,
    database: MetadataDatabase = Depends(get_database),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    repository = _get_repository(database)
    current = repository.get_datasource_connection(connection_id)

    if current is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error_code": "CONNECTION_NOT_FOUND",
                "message": "Datasource connection not found.",
            },
        )

    changes = request.model_dump(exclude_none=True)
    password = changes.pop("password", None)

    if password is not None:
        password_updated = repository.update_datasource_password(
            connection_id=connection_id,
            password=password.get_secret_value(),
            encryption_key=(
                settings.source_credential_encryption_key.get_secret_value()
            ),
        )
        if not password_updated:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={
                    "error_code": "CONNECTION_NOT_FOUND",
                    "message": "Datasource connection not found.",
                },
            )

    try:
        updated_record = repository.update_datasource_connection(
            connection_id=connection_id,
            **changes,
        )
    except IntegrityError as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "error_code": "CONNECTION_NAME_EXISTS",
                "message": "A datasource connection with this name already exists.",
            },
        ) from error

    if updated_record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error_code": "CONNECTION_NOT_FOUND",
                "message": "Datasource connection not found.",
            },
        )

    updated_record.pop("credential_reference", None)
    updated_record.pop("password_encrypted", None)
    return updated_record


@router.delete(
    "/connections/{connection_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def deactivate_database_connection(
    connection_id: int,
    database: MetadataDatabase = Depends(get_database),
) -> Response:
    repository = _get_repository(database)
    deactivated = repository.deactivate_datasource_connection(connection_id)

    if not deactivated:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error_code": "ACTIVE_CONNECTION_NOT_FOUND",
                "message": "An active datasource connection with this ID was not found.",
            },
        )

    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/discovery-runs", status_code=status.HTTP_202_ACCEPTED)
def start_discovery_run(
    request: DiscoveryRunRequest,
    background_tasks: BackgroundTasks,
    database: MetadataDatabase = Depends(get_database),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    repository = _get_repository(database)
    datasource = repository.get_datasource_connection(request.connection_id)

    if datasource is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error_code": "CONNECTION_NOT_FOUND",
                "message": "Datasource connection not found.",
            },
        )

    if not datasource.get("is_active", False):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error_code": "CONNECTION_INACTIVE",
                "message": "Datasource connection is inactive.",
            },
        )

    requested_scopes = [scope.value for scope in request.scopes]
    effective_scopes = _effective_scopes(requested_scopes)
    selected_frameworks = list(request.selected_frameworks)
    if (
        "HIPAA_COMPLIANCE" in requested_scopes
        and "HIPAA" not in selected_frameworks
    ):
        selected_frameworks.append("HIPAA")
    if selected_frameworks:
        validation = repository.validate_selected_frameworks(
            selected_frameworks
        )
        unknown_frameworks = [
            framework
            for framework in validation["unknown"]
            if framework not in SUPPORTED_FRAMEWORKS
        ]
        if unknown_frameworks:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "error_code": "UNKNOWN_COMPLIANCE_FRAMEWORK",
                    "message": "One or more framework codes are unknown.",
                    "frameworks": unknown_frameworks,
                },
            )
        unavailable_frameworks = [
            framework
            for framework in validation["unavailable"]
            if framework not in {"DPDP", "CCPA_CPRA", "PIPEDA"}
        ]
        if unavailable_frameworks:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "error_code": "COMPLIANCE_FRAMEWORK_NOT_AVAILABLE",
                    "message": (
                        "One or more selected policy packs are not yet "
                        "available for assessment."
                    ),
                    "frameworks": unavailable_frameworks,
                },
            )
    run_id = uuid4()

    selected_objects = [
        selected_object.model_dump()
        for selected_object in request.selected_objects
    ]

    repository.create_run(
        run_id=run_id,
        connection_id=request.connection_id,
        requested_scopes=requested_scopes,
        effective_scopes=effective_scopes,
        selected_objects=selected_objects,
        selected_frameworks=selected_frameworks,
    )
    repository.create_run_stages(
        run_id=run_id,
        effective_scopes=effective_scopes,
    )
    background_tasks.add_task(
        run_discovery_background,
        run_id,
        settings,
    )

    return {
        "discovery_run_id": str(run_id),
        "connection_id": request.connection_id,
        "requested_scopes": requested_scopes,
        "effective_scopes": effective_scopes,
        "selected_objects": selected_objects,
        "selected_frameworks": selected_frameworks,
        "status": "PENDING",
    }


@router.get("/discovery-runs/{run_id}")
def get_discovery_run(
    run_id: UUID,
    database: MetadataDatabase = Depends(get_database),
) -> dict[str, Any]:
    return _require_discovery_run(_get_repository(database), run_id)


@router.get("/discovery-runs/{run_id}/stages")
def get_discovery_run_stages(
    run_id: UUID,
    database: MetadataDatabase = Depends(get_database),
) -> list[dict[str, Any]]:
    repository = _get_repository(database)
    _require_discovery_run(repository, run_id)
    return repository.get_run_stages(run_id)


@router.get(
    "/discovery-runs/{run_id}/overview",
    response_model=DiscoveryRunOverviewResponse,
)
def get_discovery_overview(
    run_id: UUID,
    database: MetadataDatabase = Depends(get_database),
) -> dict[str, Any]:
    repository = _get_repository(database)
    _require_discovery_run(repository, run_id)
    return repository.get_overview(run_id)


@router.get("/discovery-runs/{run_id}/table-profiles")
def get_table_profiles(
    run_id: UUID,
    database: MetadataDatabase = Depends(get_database),
) -> list[dict[str, Any]]:
    repository = _get_repository(database)
    _require_discovery_run(repository, run_id)
    return repository.get_table_profiles_result(run_id)


@router.get(
    "/discovery-runs/{run_id}/classifications",
    response_model=PaginatedClassificationsResponse,
    summary="Get Column Classifications",
    description=(
        "Retrieves column classifications with server-side search, "
        "filtering, and pagination."
    ),
)
async def get_column_classifications(
    run_id: UUID = Path(..., description="The UUID of the discovery run"),
    classification: str | None = Query(
        None,
        description=(
            "Filter by classification type (e.g., PHI, PII, Financial, "
            "Sensitive, Public)"
        ),
    ),
    search: str | None = Query(
        None,
        description="Case-insensitive search matching table_name or column_name",
    ),
    limit: int = Query(
        50,
        ge=1,
        le=500,
        description="Number of records to return per page",
    ),
    offset: int = Query(0, ge=0, description="Number of records to skip"),
    database: MetadataDatabase = Depends(get_database),
) -> PaginatedClassificationsResponse:
    repository = _get_repository(database)
    await asyncio.to_thread(_require_discovery_run, repository, run_id)
    page = await asyncio.to_thread(
        repository.get_classifications_page,
        run_id,
        classification=classification,
        search=search,
        limit=limit,
        offset=offset,
    )
    return PaginatedClassificationsResponse(
        run_id=str(run_id),
        total_count=page["total_count"],
        limit=limit,
        offset=offset,
        counts_by_category=page["counts_by_category"],
        items=page["items"],
    )


@router.get(
    "/discovery-runs/{run_id}/dependencies",
    response_model=FullLineageResponse,
    summary="Get Dependencies",
    description="Retrieves full dependency/lineage graph for a discovery run.",
)
async def get_dependencies(
    run_id: UUID = Path(..., description="The UUID of the discovery run"),
    database: MetadataDatabase = Depends(get_database),
) -> FullLineageResponse:
    repository = _get_repository(database)
    await asyncio.to_thread(_require_discovery_run, repository, run_id)
    node_records = await asyncio.to_thread(
        repository.get_lineage_nodes_result,
        run_id,
    )
    edge_records = await asyncio.to_thread(
        repository.get_dependencies_result,
        run_id,
    )
    nodes = [_lineage_node(record) for record in node_records]
    edges = [
        LineageEdge(
            from_node=str(edge["source_object_id"]),
            to_node=str(edge["target_object_id"]),
            **_lineage_edge_values(edge),
        )
        for edge in edge_records
    ]
    return FullLineageResponse(
        run_id=str(run_id),
        nodes=nodes,
        edges=edges,
    )


@router.get(
    "/discovery-runs/{run_id}/dependencies/{object_id}",
    response_model=FocusedLineageResponse,
    summary="Get Focused Dependencies",
    description=(
        "Retrieves direct upstream (parents) and downstream (children) "
        "dependencies for a specific object."
    ),
)
async def get_focused_dependencies(
    run_id: UUID = Path(..., description="The UUID of the discovery run"),
    object_id: int = Path(..., description="The discovered object ID"),
    database: MetadataDatabase = Depends(get_database),
) -> FocusedLineageResponse:
    repository = _get_repository(database)
    await asyncio.to_thread(_require_discovery_run, repository, run_id)
    node_records = await asyncio.to_thread(
        repository.get_lineage_nodes_result,
        run_id,
    )
    target_record = next(
        (
            record
            for record in node_records
            if int(record["object_id"]) == object_id
        ),
        None,
    )
    if target_record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                f"Object '{object_id}' or run '{run_id}' not found."
            ),
        )

    edges = await asyncio.to_thread(
        repository.get_dependencies_result,
        run_id,
        object_id,
    )
    upstream = []
    downstream = []

    for edge in edges:
        edge_values = _lineage_edge_values(
            edge
        )

        if (
            int(edge["target_object_id"])
            == object_id
        ):
            source_schema = str(
                edge.get("source_schema")
                or ""
            ).strip()

            source_object = str(
                edge.get("source_object")
                or ""
            ).strip()

            source_qualified_name = (
                f"{source_schema}.{source_object}"
                if source_schema
                else source_object
            )

            upstream.append(
                FocusedLineageItem(
                    id=str(
                        edge["source_object_id"]
                    ),
                    schema_name=source_schema,
                    object_name=source_object,
                    qualified_name=(
                        source_qualified_name
                    ),
                    type=str(
                        edge[
                            "source_object_type"
                        ]
                    ).lower(),
                    **edge_values,
                )
            )

        if (
            int(edge["source_object_id"])
            == object_id
        ):
            target_schema = str(
                edge.get("target_schema")
                or ""
            ).strip()

            target_object = str(
                edge.get("target_object")
                or ""
            ).strip()

            target_qualified_name = (
                f"{target_schema}.{target_object}"
                if target_schema
                else target_object
            )

            downstream.append(
                FocusedLineageItem(
                    id=str(
                        edge["target_object_id"]
                    ),
                    schema_name=target_schema,
                    object_name=target_object,
                    qualified_name=(
                        target_qualified_name
                    ),
                    type=str(
                        edge[
                            "target_object_type"
                        ]
                    ).lower(),
                    **edge_values,
                )
            )

    return FocusedLineageResponse(
        run_id=str(run_id),
        target_object=_lineage_node(target_record),
        upstream=upstream,
        downstream=downstream,
    )


@router.get("/discovery-runs/{run_id}/compliance-results")
def get_compliance_results(
    run_id: UUID,
    database: MetadataDatabase = Depends(get_database),
) -> dict[str, Any]:
    repository = _get_repository(database)
    _require_discovery_run(repository, run_id)
    results = repository.get_compliance_results(run_id)
    return {
        "discovery_run_id": str(run_id),
        "framework_count": len(results),
        "frameworks": results,
    }


@router.get("/compliance-assessments/{assessment_id}/control-evidence")
def get_control_evidence(
    assessment_id: int,
    database: MetadataDatabase = Depends(get_database),
) -> dict[str, Any]:
    if assessment_id <= 0:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="assessment_id must be greater than zero",
        )
    evidence = _get_repository(database).list_control_evidence(assessment_id)
    return {
        "assessment_id": assessment_id,
        "evidence_count": len(evidence),
        "evidence": evidence,
    }


@router.put(
    "/compliance-assessments/{assessment_id}/controls/{control_code}/evidence"
)
def submit_control_evidence(
    assessment_id: int,
    control_code: str,
    request: ControlEvidenceInput,
    database: MetadataDatabase = Depends(get_database),
) -> dict[str, Any]:
    repository = _get_repository(database)
    payload = request.model_dump(mode="json")
    payload["verification_status"] = request.verification_status.value
    try:
        evidence = repository.upsert_control_evidence(
            assessment_id=assessment_id,
            control_code=control_code.strip().upper(),
            payload=payload,
        )
    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error_code": "COMPLIANCE_CONTROL_NOT_FOUND",
                "message": str(error),
            },
        ) from error
    return {
        "message": "Evidence saved and assessment recalculated.",
        "evidence": evidence,
    }





@router.get("/discovery-runs/{run_id}/export")
def export_discovery_run(
    run_id: UUID,
    database: MetadataDatabase = Depends(get_database),
) -> JSONResponse:
    repository = _get_repository(database)
    run = _require_discovery_run(repository, run_id)
    payload = {
        "run": run,
        "stages": repository.get_run_stages(
            run_id
        ),
        "overview": repository.get_overview(
            run_id
        ),
        "table_profiles": (
            repository.get_table_profiles_result(
                run_id
            )
        ),
        "classifications": (
            repository.get_classifications_result(
                run_id
            )
        ),
        "dependencies": (
            repository.get_dependencies_result(
                run_id
            )
        ),
        "compliance_results": (
            repository.get_compliance_results(
                run_id
            )
        ),
    }

    return JSONResponse(
        content=jsonable_encoder(payload),
        headers={
            "Content-Disposition": (
                f'attachment; filename="discovery-{run_id}.json"'
            )
        },
    )
