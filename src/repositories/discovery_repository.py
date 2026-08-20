from __future__ import annotations
import json
from typing import Any
from uuid import UUID
from sqlalchemy import text
from src.services.database import MetadataDatabase


class DiscoveryRepository:
    def __init__(self, database: MetadataDatabase):
        self.database = database

    def create_run(self, run_id: UUID, connection_id: int, scopes: list[str]) -> None:
        query = text("""
            INSERT INTO discovery_runs
                (discovery_run_id, connection_id, requested_scopes, status)
            VALUES
                (:run_id, :connection_id, CAST(:scopes AS jsonb), 'PENDING')
        """)
        with self.database.connect() as connection:
            connection.execute(query, {
                "run_id": str(run_id),
                "connection_id": connection_id,
                "scopes": json.dumps(scopes),
            })

    def update_run_status(self, run_id: UUID, status: str, current_stage: str | None = None) -> None:
        query = text("""
            UPDATE discovery_runs
               SET status = :status,
                   current_stage = :current_stage,
                   updated_at = CURRENT_TIMESTAMP
             WHERE discovery_run_id = :run_id
        """)
        with self.database.connect() as connection:
            connection.execute(query, {
                "run_id": str(run_id),
                "status": status,
                "current_stage": current_stage,
            })

    def get_run(self, run_id: UUID) -> dict[str, Any] | None:
        query = text("SELECT * FROM discovery_runs WHERE discovery_run_id = :run_id")
        with self.database.connect() as connection:
            row = connection.execute(query, {"run_id": str(run_id)}).mappings().one_or_none()
        return dict(row) if row else None
