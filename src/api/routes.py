from __future__ import annotations

from uuid import UUID, uuid4

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy.exc import IntegrityError

from src.api.dependencies import get_database
from src.jobs.discovery_runner import run_discovery_background
from src.models.schemas import ConnectionInput, DiscoveryRunRequest
from src.repositories.discovery_repository import DiscoveryRepository
from src.services.database import MetadataDatabase
from src.tools.connection_tools import test_connection
from src.utils.config import Settings, get_settings


router = APIRouter()


def _safe_config(request: ConnectionInput) -> dict:
    return {
        "host": request.host,
        "port": request.port,
        "database_name": request.database_name,
        "username": request.username,
        "ssl_enabled": request.ssl_enabled,
    }


def _effective_scopes(requested_scopes: list[str]) -> list[str]:
    effective = set(requested_scopes)
    if "HIPAA_COMPLIANCE" in effective:
        effective.add("COLUMN_CLASSIFICATION")
    return sorted(effective)


@router.get("/health")
def health() -> dict:
    return {"status": "ok"}


@router.post("/connections/test")
def test_database_connection(request: ConnectionInput) -> dict:
    result = test_connection(
        database_type=request.database_type,
        safe_config=_safe_config(request),
        password=request.password.get_secret_value(),
    )
    if not result.success:
        raise HTTPException(status_code=400, detail=result.message)
    return {
        "status": "SUCCESS",
        "message": result.message,
        "response_time_ms": result.response_time_ms,
    }


@router.post("/connections", status_code=201)
def create_database_connection(
    request: ConnectionInput,
    database: MetadataDatabase = Depends(get_database),
) -> dict:
    test_result = test_connection(
        database_type=request.database_type,
        safe_config=_safe_config(request),
        password=request.password.get_secret_value(),
    )
    if not test_result.success:
        raise HTTPException(
            status_code=400,
            detail=(
                "Datasource was not saved because the connection test failed. "
                f"{test_result.message}"
            ),
        )

    repository = DiscoveryRepository(database)
    try:
        saved = repository.create_datasource_connection(
            connection_name=request.connection_name,
            database_type=request.database_type.value,
            host=request.host,
            port=request.port,
            database_name=request.database_name,
            username=request.username,
            password=request.password.get_secret_value(),
            ssl_enabled=request.ssl_enabled,
        )
    except IntegrityError as error:
        raise HTTPException(
            status_code=409,
            detail="A datasource connection with this name already exists",
        ) from error

    return {
        **saved,
        "connection_test": {
            "status": "SUCCESS",
            "response_time_ms": test_result.response_time_ms,
        },
    }


@router.post("/discovery-runs", status_code=202)
def start_discovery_run(
    request: DiscoveryRunRequest,
    background_tasks: BackgroundTasks,
    database: MetadataDatabase = Depends(get_database),
    settings: Settings = Depends(get_settings),
) -> dict:
    repository = DiscoveryRepository(database)
    datasource = repository.get_datasource_connection(request.connection_id)

    if datasource is None:
        raise HTTPException(status_code=404, detail="Datasource connection not found")
    if not datasource.get("is_active", False):
        raise HTTPException(status_code=400, detail="Datasource connection is inactive")
    if not request.scopes:
        raise HTTPException(status_code=400, detail="At least one discovery scope is required")

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
) -> dict:
    repository = DiscoveryRepository(database)
    record = repository.get_run(run_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Discovery run not found")
    return record


@router.get("/discovery-runs/{run_id}/stages")
def get_discovery_run_stages(
    run_id: UUID,
    database: MetadataDatabase = Depends(get_database),
) -> list[dict]:
    repository = DiscoveryRepository(database)
    if repository.get_run(run_id) is None:
        raise HTTPException(status_code=404, detail="Discovery run not found")
    return repository.get_run_stages(run_id)
