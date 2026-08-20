from uuid import UUID
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from src.models.schemas import ConnectionInput, DiscoveryRunRequest
from src.repositories.discovery_repository import DiscoveryRepository
from src.services.database import MetadataDatabase
from src.api.dependencies import get_database

router = APIRouter()


@router.get("/health")
def health() -> dict:
    return {"status": "ok"}


@router.post("/connections/test")
def test_database_connection(request: ConnectionInput) -> dict:
    # Wire to Connection Management Service and vendor connector tools.
    return {"status": "NOT_IMPLEMENTED", "message": "Add vendor connection adapter."}


@router.post("/discovery-runs")
def start_discovery_run(
    request: DiscoveryRunRequest,
    background_tasks: BackgroundTasks,
    database: MetadataDatabase = Depends(get_database),
) -> dict:
    # Production version should submit to a durable worker queue.
    # FastAPI BackgroundTasks is only an MVP placeholder.
    from uuid import uuid4
    run_id = uuid4()
    repository = DiscoveryRepository(database)
    repository.create_run(run_id, request.connection_id, [scope.value for scope in request.scopes])
    return {
        "discovery_run_id": str(run_id),
        "connection_id": request.connection_id,
        "status": "PENDING",
    }


@router.get("/discovery-runs/{run_id}")
def get_discovery_run(
    run_id: UUID,
    database: MetadataDatabase = Depends(get_database),
) -> dict:
    record = DiscoveryRepository(database).get_run(run_id)
    if not record:
        raise HTTPException(status_code=404, detail="Discovery run not found")
    return record
