from __future__ import annotations

import logging
from typing import Any
from uuid import UUID, uuid4

from fastapi import (
    Body,
    APIRouter,
    BackgroundTasks,
    Depends,
    HTTPException,
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
)
from src.models.compliance_schemas import (
    RemediateFindingRequest,
    UpdateRemediationStandardsRequest,
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


# After
# def _effective_scopes(requested_scopes: list[str]) -> list[str]:
#     """Add internal workflow dependencies required for execution."""
#     effective_scopes = set(requested_scopes)

#     if "REGULATORY_COMPLIANCE" in effective_scopes:
#         effective_scopes.add("COLUMN_CLASSIFICATION")

#     return sorted(effective_scopes)
# def _effective_scopes(
#     requested_scopes: list[str],
#     selected_frameworks: list[str] | None = None,
# ) -> list[str]:
#     """Add internal workflow dependencies required for execution."""
#     effective_scopes = set(requested_scopes)

#     # Auto-enable compliance and classification when frameworks are selected
#     if selected_frameworks or "REGULATORY_COMPLIANCE" in effective_scopes:
#         effective_scopes.add("COLUMN_CLASSIFICATION")
#         effective_scopes.add("REGULATORY_COMPLIANCE")

#     return sorted(effective_scopes)

# +++ AFTER +++
def _effective_scopes(
    requested_scopes: list[str],
    selected_frameworks: list[str] | None = None,
) -> list[str]:
    """Add internal workflow dependencies required for execution."""
    effective_scopes = set(requested_scopes)

    # When compliance or frameworks are requested, activate both classification and compliance
    if (
        selected_frameworks
        or "REGULATORY_COMPLIANCE" in effective_scopes
        or "HIPAA_COMPLIANCE" in effective_scopes
    ):
        effective_scopes.add("COLUMN_CLASSIFICATION")
        effective_scopes.add("REGULATORY_COMPLIANCE")

    return sorted(effective_scopes)

def _get_repository(database: MetadataDatabase) -> DiscoveryRepository:
    return DiscoveryRepository(database)


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

    runs = repository.list_connection_runs(connection_id)
    if runs:
        latest = runs[0]
        record["discovery_status"] = latest.get("status") or record.get("discovery_status")
        record["last_discovered_at"] = (
            latest.get("completed_at")
            or latest.get("started_at")
            or latest.get("created_at")
            or record.get("last_discovered_at")
        )
        record["latest_run_id"] = latest.get("discovery_run_id")
    else:
        record.setdefault("latest_run_id", None)

    record.pop("credential_reference", None)
    record.pop("password_encrypted", None)
    return record

@router.get("/connections/{connection_id}/runs")
def list_connection_runs(
    connection_id: int,
    database: MetadataDatabase = Depends(get_database),
) -> dict[str, Any]:
    """Return chronological discovery run history for a datasource connection."""
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

    runs = repository.list_connection_runs(connection_id)
    return {
        "connection_id": connection_id,
        "connection_name": datasource.get("connection_name"),
        "database_type": datasource.get("database_type"),
        "host": datasource.get("host"),
        "port": datasource.get("port"),
        "database_name": datasource.get("database_name"),
        "schema_name": datasource.get("schema_name"),
        "total_runs": len(runs),
        "latest_run_id": runs[0]["discovery_run_id"] if runs else None,
        "runs": runs,
    }

@router.get("/connections/{connection_id}/latest-discovery")
def get_latest_discovery_for_connection(
    connection_id: int,
    database: MetadataDatabase = Depends(get_database),
) -> dict[str, Any]:
    """Return latest discovery run details and result endpoints for a connection."""
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

    runs = repository.list_connection_runs(connection_id)
    if not runs:
        return {
            "connection_id": connection_id,
            "connection_name": datasource.get("connection_name"),
            "has_discovery": False,
            "discovery_status": "NOT_STARTED",
            "latest_run_id": None,
            "last_discovered_at": None,
            "runs_url": f"/api/v1/connections/{connection_id}/runs",
            "results_base_url": None,
        }

    latest = runs[0]
    run_id = latest.get("discovery_run_id")
    last_discovered = (
        latest.get("completed_at")
        or latest.get("started_at")
        or latest.get("created_at")
    )

    return {
        "connection_id": connection_id,
        "connection_name": datasource.get("connection_name"),
        "has_discovery": True,
        "discovery_status": latest.get("status"),
        "latest_run_id": run_id,
        "last_discovered_at": last_discovered,
        "runs_url": f"/api/v1/connections/{connection_id}/runs",
        "results_base_url": f"/api/v1/discovery-runs/{run_id}",
        "run": latest,
    }

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

    # requested_scopes = [scope.value for scope in request.scopes]
    # effective_scopes = _effective_scopes(requested_scopes)
    # selected_frameworks = list(request.selected_frameworks)
    # # if (
    # #     "HIPAA_COMPLIANCE" in requested_scopes
    # #     and "HIPAA" not in selected_frameworks
    # # ):
    # #     selected_frameworks.append("HIPAA")
    # if selected_frameworks:
    #     validation = repository.validate_selected_frameworks(
    #         selected_frameworks
    #     )
    #     if validation["unknown"]:
    #         raise HTTPException(
    #             status_code=status.HTTP_400_BAD_REQUEST,
    #             detail={
    #                 "error_code": "UNKNOWN_COMPLIANCE_FRAMEWORK",
    #                 "message": "One or more framework codes are unknown.",
    #                 "frameworks": validation["unknown"],
    #             },
    #         )
    #     if validation["unavailable"]:
    #         raise HTTPException(
    #             status_code=status.HTTP_400_BAD_REQUEST,
    #             detail={
    #                 "error_code": "COMPLIANCE_FRAMEWORK_NOT_AVAILABLE",
    #                 "message": (
    #                     "One or more selected policy packs are not yet "
    #                     "available for assessment."
    #                 ),
    #                 "frameworks": validation["unavailable"],
    #             },
    #         )
    #     selected_frameworks = validation["available"]
    # run_id = uuid4()

    # +++ AFTER +++
    requested_scopes = [scope.value for scope in request.scopes]
    selected_frameworks = list(request.selected_frameworks)

    # Validate selected frameworks against the new Stage 4 engine
    from src.policies.compliance_mapping import FRAMEWORK_SCOPES
    supported_frameworks = set(FRAMEWORK_SCOPES.keys())

    if selected_frameworks:
        unknown = [
            fw for fw in selected_frameworks
            if fw.upper().strip() not in supported_frameworks
        ]
        if unknown:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "error_code": "UNKNOWN_COMPLIANCE_FRAMEWORK",
                    "message": (
                        f"Unsupported framework(s): {', '.join(unknown)}. "
                        f"Supported: {', '.join(sorted(supported_frameworks))}"
                    ),
                },
            )

    effective_scopes = _effective_scopes(requested_scopes, selected_frameworks)
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


@router.get("/discovery-runs/{run_id}/overview")
def get_discovery_overview(
    run_id: UUID,
    database: MetadataDatabase = Depends(get_database),
) -> dict[str, Any]:
    repository = _get_repository(database)
    _require_discovery_run(repository, run_id)
    return repository.get_overview(run_id)

@router.get("/discovery-runs/{run_id}/objects")
def get_discovered_objects(
    run_id: UUID,
    database: MetadataDatabase = Depends(get_database),
) -> dict[str, Any]:
    repository = _get_repository(database)
    _require_discovery_run(repository, run_id)
    return repository.get_discovered_objects_result(run_id)

@router.get("/discovery-runs/{run_id}/table-profiles")
def get_table_profiles(
    run_id: UUID,
    database: MetadataDatabase = Depends(get_database),
) -> list[dict[str, Any]]:
    repository = _get_repository(database)
    _require_discovery_run(repository, run_id)
    return repository.get_table_profiles_result(run_id)


@router.get("/discovery-runs/{run_id}/classifications")
def get_classifications(
    run_id: UUID,
    database: MetadataDatabase = Depends(get_database),
) -> list[dict[str, Any]]:
    repository = _get_repository(database)
    _require_discovery_run(repository, run_id)
    return repository.get_classifications_result(run_id)


@router.get("/discovery-runs/{run_id}/dependencies")
def get_dependencies(
    run_id: UUID,
    database: MetadataDatabase = Depends(get_database),
) -> list[dict[str, Any]]:
    repository = _get_repository(database)
    _require_discovery_run(repository, run_id)
    return repository.get_dependencies_result(run_id)


@router.get("/discovery-runs/{run_id}/dependencies/{object_id}")
def get_focused_dependencies(
    run_id: UUID,
    object_id: int,
    database: MetadataDatabase = Depends(get_database),
) -> dict[str, Any]:
    repository = _get_repository(database)
    _require_discovery_run(repository, run_id)
    edges = repository.get_dependencies_result(
        run_id=run_id,
        object_id=object_id,
    )

    return {
        "object_id": object_id,
        "upstream": [
            edge for edge in edges if edge["target_object_id"] == object_id
        ],
        "downstream": [
            edge for edge in edges if edge["source_object_id"] == object_id
        ],
        "edges": edges,
    }


# @router.get("/discovery-runs/{run_id}/compliance-results")
# def get_compliance_results(
#     run_id: UUID,
#     database: MetadataDatabase = Depends(get_database),
# ) -> dict[str, Any]:
#     repository = _get_repository(database)
#     _require_discovery_run(repository, run_id)
#     results = repository.get_compliance_results(run_id)
#     return {
#         "discovery_run_id": str(run_id),
#         "framework_count": len(results),
#         "frameworks": results,
#     }

# +++ AFTER +++
@router.get("/discovery-runs/{run_id}/compliance-results")
def get_compliance_results(
    run_id: UUID,
    database: MetadataDatabase = Depends(get_database),
) -> dict[str, Any]:
    from src.repositories.compliance_repository import ComplianceRepository

    repository = _get_repository(database)
    _require_discovery_run(repository, run_id)

    comp_repo = ComplianceRepository(database)
    results = comp_repo.get_compliance_results(run_id)

    return {
        "discovery_run_id": str(run_id),
        "framework_count": len(results),
        "frameworks": results,
    }


def _execute_remediation_update(
    run_id: UUID,
    payload: RemediateFindingRequest,
    database: MetadataDatabase,
) -> dict[str, Any]:
    from src.repositories.compliance_repository import ComplianceRepository

    repository = _get_repository(database)
    _require_discovery_run(repository, run_id)

    comp_repo = ComplianceRepository(database)
    try:
        result = comp_repo.remediate_finding_across_frameworks(
            discovery_run_id=run_id,
            table_name=payload.table_name,
            column_name=payload.column_name,
            remediation_action=payload.remediation_action,
            remediation_status=(
                payload.remediation_status.value
                if payload.remediation_status
                else None
            ),
            remediated_by=payload.remediated_by,
            remediation_notes=payload.remediation_notes,
            action_type=(
                payload.action_type.value if payload.action_type else None
            ),
            assigned_to=payload.assigned_to,
            due_date=payload.due_date,
            justification=payload.justification,
            approved_by=payload.approved_by,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    if result["remediated_findings_count"] == 0:
        raise HTTPException(
            status_code=404,
            detail=(
                f"No compliance findings found for {payload.table_name}.{payload.column_name} "
                f"in discovery run {run_id}"
            ),
        )

    return result


@router.get("/discovery-runs/{run_id}/remediation")
def get_remediation_workspace(
    run_id: UUID,
    status: str | None = None,
    search: str | None = None,
    database: MetadataDatabase = Depends(get_database),
) -> dict[str, Any]:
    from src.repositories.compliance_repository import ComplianceRepository

    repository = _get_repository(database)
    _require_discovery_run(repository, run_id)

    comp_repo = ComplianceRepository(database)
    return comp_repo.get_remediation_workspace(
        discovery_run_id=run_id,
        status_filter=status,
        search=search,
    )


@router.patch("/discovery-runs/{run_id}/remediation")
def update_remediation_finding(
    run_id: UUID,
    payload: RemediateFindingRequest,
    database: MetadataDatabase = Depends(get_database),
) -> dict[str, Any]:
    return _execute_remediation_update(run_id, payload, database)





@router.get("/remediation-standards")
def get_remediation_standards(
    database: MetadataDatabase = Depends(get_database),
) -> dict[str, Any]:
    from src.repositories.compliance_repository import ComplianceRepository

    comp_repo = ComplianceRepository(database)
    return comp_repo.get_remediation_standards()


@router.put("/remediation-standards")
def update_remediation_standards(
    payload: UpdateRemediationStandardsRequest,
    database: MetadataDatabase = Depends(get_database),
) -> dict[str, Any]:
    from src.repositories.compliance_repository import ComplianceRepository

    comp_repo = ComplianceRepository(database)
    return comp_repo.update_remediation_standards(
        critical_sla_days=payload.critical_sla_days,
        serious_sla_days=payload.serious_sla_days,
        needs_review_sla_days=payload.needs_review_sla_days,
        min_justification_chars=payload.min_justification_chars,
        require_lead_signoff=payload.require_lead_signoff,
        preferred_fixes=payload.preferred_fixes,
        updated_by=payload.updated_by,
    )
# @router.get("/discovery-runs/{run_id}/compliance-results")
# def get_compliance_results(
#     run_id: UUID,
#     database: MetadataDatabase = Depends(get_database),
# ) -> dict[str, Any]:
#     import traceback
#     try:
#         from src.repositories.compliance_repository import ComplianceRepository

#         repository = _get_repository(database)
#         _require_discovery_run(repository, run_id)

#         comp_repo = ComplianceRepository(database)
#         results = comp_repo.get_compliance_results(run_id)

#         return {
#             "discovery_run_id": str(run_id),
#             "framework_count": len(results),
#             "frameworks": results,
#         }
#     except Exception as exc:
#         print("\n" + "=" * 50)
#         print("EXACT ERROR IN /compliance-results:")
#         traceback.print_exc()
#         print("=" * 50 + "\n")
#         raise HTTPException(
#             status_code=500,
#             detail={
#                 "error_type": exc.__class__.__name__,
#                 "error_message": str(exc),
#                 "traceback": traceback.format_exc().splitlines()[-4:],
#             },
#         )

# @router.get("/compliance-assessments/{assessment_id}/control-evidence")
# def get_control_evidence(
#     assessment_id: int,
#     database: MetadataDatabase = Depends(get_database),
# ) -> dict[str, Any]:
#     if assessment_id <= 0:
#         raise HTTPException(
#             status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
#             detail="assessment_id must be greater than zero",
#         )
#     evidence = _get_repository(database).list_control_evidence(assessment_id)
#     return {
#         "assessment_id": assessment_id,
#         "evidence_count": len(evidence),
#         "evidence": evidence,
#     }


# @router.put(
#     "/compliance-assessments/{assessment_id}/controls/{control_code}/evidence"
# )
# def submit_control_evidence(
#     assessment_id: int,
#     control_code: str,
#     request: ControlEvidenceInput,
#     database: MetadataDatabase = Depends(get_database),
# ) -> dict[str, Any]:
#     repository = _get_repository(database)
#     payload = request.model_dump(mode="json")
#     payload["verification_status"] = request.verification_status.value
#     try:
#         evidence = repository.upsert_control_evidence(
#             assessment_id=assessment_id,
#             control_code=control_code.strip().upper(),
#             payload=payload,
#         )
#     except ValueError as error:
#         raise HTTPException(
#             status_code=status.HTTP_404_NOT_FOUND,
#             detail={
#                 "error_code": "COMPLIANCE_CONTROL_NOT_FOUND",
#                 "message": str(error),
#             },
#         ) from error
#     return {
#         "message": "Evidence saved and assessment recalculated.",
#         "evidence": evidence,
#     }


# @router.get("/discovery-runs/{run_id}/hipaa-findings")
# def get_hipaa_findings(
#     run_id: UUID,
#     database: MetadataDatabase = Depends(get_database),
# ) -> dict[str, Any]:
#     repository = _get_repository(database)
#     _require_discovery_run(repository, run_id)
#     return repository.get_hipaa_result(run_id)


@router.get("/discovery-runs/{run_id}/export")
def export_discovery_run(
    run_id: UUID,
    database: MetadataDatabase = Depends(get_database),
) -> JSONResponse:
    from src.agents.report_agent import ReportGenerationAgent
    from src.repositories.compliance_repository import ComplianceRepository

    repository = _get_repository(database)
    run = _require_discovery_run(repository, run_id)
    comp_repo = ComplianceRepository(database)

    datasource = repository.get_datasource_for_run(run_id)
    objects = repository.get_discovered_objects_result(run_id)
    table_profiles = repository.get_table_profiles_result(run_id)
    classifications = repository.get_classifications_result(run_id)
    dependencies = repository.get_dependencies_result(run_id)
    compliance_results = comp_repo.get_compliance_results(run_id)

    state = {
        "discovery_run_id": str(run_id),
        "connection_id": run.get("connection_id") if isinstance(run, dict) else getattr(run, "connection_id", None),
        "status": run.get("status") if isinstance(run, dict) else getattr(run, "status", None),
        "requested_scopes": run.get("requested_scopes") if isinstance(run, dict) else [],
        "effective_scopes": run.get("effective_scopes") if isinstance(run, dict) else [],
        "selected_objects": run.get("selected_objects") if isinstance(run, dict) else [],
        "selected_frameworks": run.get("selected_frameworks") if isinstance(run, dict) else [],
        "datasource": datasource,
        "objects": objects,
        "table_profiles": table_profiles,
        "classifications": classifications,
        "dependencies": dependencies,
        "compliance_results": compliance_results,
    }

    report = ReportGenerationAgent().build(state)

    return JSONResponse(
        content=jsonable_encoder(report),
        headers={
            "Content-Disposition": (
                f'attachment; filename="discovery-{run_id}.json"'
            )
        },
    )
