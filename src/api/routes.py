from __future__ import annotations

import logging
from typing import Any
from uuid import UUID, uuid4

from fastapi import (
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
from src.models.schemas import (
    ConnectionInput,
    ConnectionUpdate,
    DiscoveryRunRequest,
)
from src.repositories.discovery_repository import DiscoveryRepository
from src.services.database import MetadataDatabase
from src.tools.connection_tools import test_connection
from src.utils.config import Settings, get_settings


logger = logging.getLogger(__name__)
router = APIRouter()


def _safe_config(request: ConnectionInput) -> dict[str, Any]:
    """Build the non-secret source-database configuration."""
    return {
        "host": request.host,
        "port": request.port,
        "database_name": request.database_name,
        "username": request.username,
        "ssl_enabled": request.ssl_enabled,
    }


def _effective_scopes(requested_scopes: list[str]) -> list[str]:
    """Add internal workflow dependencies required for execution."""
    effective_scopes = set(requested_scopes)

    if "HIPAA_COMPLIANCE" in effective_scopes:
        effective_scopes.add("COLUMN_CLASSIFICATION")

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
        record.pop("password_plaintext", None)

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
    record.pop("password_plaintext", None)
    return record


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
    updated_record.pop("password_plaintext", None)
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
    run_id = uuid4()

    repository.create_run(
        run_id=run_id,
        connection_id=request.connection_id,
        requested_scopes=requested_scopes,
        effective_scopes=effective_scopes,
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


@router.get("/discovery-runs/{run_id}/hipaa-findings")
def get_hipaa_findings(
    run_id: UUID,
    database: MetadataDatabase = Depends(get_database),
) -> dict[str, Any]:
    repository = _get_repository(database)
    _require_discovery_run(repository, run_id)
    return repository.get_hipaa_result(run_id)


@router.get("/discovery-runs/{run_id}/export")
def export_discovery_run(
    run_id: UUID,
    database: MetadataDatabase = Depends(get_database),
) -> JSONResponse:
    repository = _get_repository(database)
    run = _require_discovery_run(repository, run_id)
    payload = {
        "run": run,
        "stages": repository.get_run_stages(run_id),
        "overview": repository.get_overview(run_id),
        "table_profiles": repository.get_table_profiles_result(run_id),
        "classifications": repository.get_classifications_result(run_id),
        "dependencies": repository.get_dependencies_result(run_id),
        "hipaa": repository.get_hipaa_result(run_id),
    }

    return JSONResponse(
        content=jsonable_encoder(payload),
        headers={
            "Content-Disposition": (
                f'attachment; filename="discovery-{run_id}.json"'
            )
        },
    )
