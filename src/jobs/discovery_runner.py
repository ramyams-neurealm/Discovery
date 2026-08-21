from __future__ import annotations

import logging
from uuid import UUID

from src.agents.classification_agent import DataClassificationAgent
from src.agents.dependency_mapping_agent import DependencyMappingAgent
from src.agents.hipaa_compliance_score_agent import HipaaComplianceScoreAgent
from src.agents.metadata_profiling_agent import MetadataDiscoveryProfilingAgent
from src.agents.report_agent import ReportGenerationAgent
from src.models.enums import DatabaseType
from src.orchestration.supervisor import DiscoverySupervisor
from src.repositories.discovery_repository import DiscoveryRepository
from src.services.database import MetadataDatabase
from src.services.key_vault_service import KeyVaultService
from src.tools.connection_tools import open_source_connector
from src.utils.config import Settings


logger = logging.getLogger(__name__)


def run_discovery_background(
    discovery_run_id: UUID | str,
    settings: Settings,
) -> None:
    """Execute one discovery run outside the request-response cycle."""
    run_id = str(discovery_run_id)
    database = MetadataDatabase(settings)
    repository = DiscoveryRepository(database)
    key_vault = KeyVaultService(settings)
    source_connector = None

    try:
        run = repository.get_run(run_id)
        if run is None:
            raise LookupError("Discovery run was not found")

        datasource = repository.get_datasource_for_run(run_id)
        if datasource is None:
            repository.update_run_status(
                run_id=run_id,
                status="FAILED",
                current_stage="CONNECTION_VALIDATION",
                progress_percentage=0,
                error_code="DATASOURCE_NOT_FOUND",
                error_message="Datasource connection was not found",
            )
            return

        if not datasource.get("is_active", False):
            repository.update_run_status(
                run_id=run_id,
                status="FAILED",
                current_stage="CONNECTION_VALIDATION",
                progress_percentage=0,
                error_code="DATASOURCE_INACTIVE",
                error_message="Datasource connection is inactive",
            )
            return

        password = datasource.get("password_plaintext")
        if not password:
            repository.update_run_status(
                run_id=run_id,
                status="FAILED",
                current_stage="CONNECTION_VALIDATION",
                progress_percentage=0,
                error_code="DATASOURCE_PASSWORD_MISSING",
                error_message="Datasource password is not available",
            )
            return

        repository.update_stage(
            run_id=run_id,
            stage_name="CONNECTION_VALIDATION",
            stage_status="RUNNING",
            message="Connecting to datasource",
        )
        repository.update_run_status(
            run_id=run_id,
            status="RUNNING",
            current_stage="CONNECTION_VALIDATION",
            progress_percentage=2,
        )

        safe_config = {
            "host": datasource["host"],
            "port": datasource["port"],
            "database_name": datasource["database_name"],
            "username": datasource["username"],
            "ssl_enabled": datasource["ssl_enabled"],
        }
        if datasource.get("schema_name"):
            safe_config["schema_name"] = datasource["schema_name"]

        database_type = DatabaseType(datasource["database_type"])
        source_connector = open_source_connector(
            database_type=database_type,
            safe_config=safe_config,
            password=password,
        )

        repository.update_stage(
            run_id=run_id,
            stage_name="CONNECTION_VALIDATION",
            stage_status="COMPLETED",
            message="Datasource connection successful",
            processed_items=1,
            total_items=1,
        )
        repository.update_run_status(
            run_id=run_id,
            status="RUNNING",
            current_stage="CONNECTION_VALIDATION",
            progress_percentage=8,
        )

        metadata_agent = MetadataDiscoveryProfilingAgent(
            settings=settings,
            key_vault=key_vault,
            repository=repository,
        )
        classification_agent = DataClassificationAgent(
            settings=settings,
            key_vault=key_vault,
        )
        dependency_agent = DependencyMappingAgent(
            settings=settings,
            key_vault=key_vault,
        )
        hipaa_agent = HipaaComplianceScoreAgent(
            settings=settings,
            key_vault=key_vault,
        )
        report_agent = ReportGenerationAgent()

        supervisor = DiscoverySupervisor(
            metadata_agent=metadata_agent,
            classification_agent=classification_agent,
            dependency_agent=dependency_agent,
            hipaa_agent=hipaa_agent,
            report_agent=report_agent,
            repository=repository,
        )

        requested_scopes = list(run.get("requested_scopes") or [])
        supervisor.invoke(
            discovery_run_id=run_id,
            connection_id=datasource["connection_id"],
            scopes=requested_scopes,
            source_connection=source_connector,
        )

    except Exception as error:
        logger.exception(
            "Discovery run failed",
            extra={"discovery_run_id": run_id},
        )
        current = repository.get_run(run_id)
        if current and current.get("status") != "FAILED":
            repository.update_run_status(
                run_id=run_id,
                status="FAILED",
                current_stage=current.get("current_stage"),
                progress_percentage=current.get("progress_percentage"),
                error_code="DISCOVERY_RUN_FAILED",
                error_message=(
                    "Discovery run failed: "
                    f"{error.__class__.__name__}"
                ),
            )
    finally:
        if source_connector is not None:
            source_connector.close()
        key_vault.close()
