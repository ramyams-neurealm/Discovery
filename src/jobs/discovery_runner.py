from __future__ import annotations

import logging
from time import perf_counter
from uuid import UUID

from src.agents.classification_agent import (
    DataClassificationAgent,
)
from src.agents.dependency_mapping_agent import (
    DependencyMappingAgent,
)
from src.agents.hipaa_compliance_score_agent import (
    HipaaComplianceScoreAgent,
)
from src.agents.metadata_profiling_agent import (
    MetadataDiscoveryProfilingAgent,
)
from src.agents.report_agent import ReportGenerationAgent
from src.models.enums import DatabaseType
from src.orchestration.supervisor import DiscoverySupervisor
from src.repositories.discovery_repository import (
    DiscoveryRepository,
)
from src.services.database import MetadataDatabase
from src.services.key_vault_service import KeyVaultService
from src.tools.connection_tools import open_source_connector
from src.utils.config import Settings


logger = logging.getLogger(__name__)


CONNECTION_VALIDATION_STAGE = "CONNECTION_VALIDATION"


def _fail_connection_validation(
    *,
    repository: DiscoveryRepository,
    run_id: str,
    error_code: str,
    message: str,
    progress_percentage: float = 0,
) -> None:
    """
    Mark both the Connection Validation stage and the overall
    Discovery run as failed.
    """

    repository.update_stage(
        run_id=run_id,
        stage_name=CONNECTION_VALIDATION_STAGE,
        stage_status="FAILED",
        message=message,
        processed_items=0,
        total_items=1,
        error_code=error_code,
        error_message=message,
    )

    repository.update_run_status(
        run_id=run_id,
        status="FAILED",
        current_stage=CONNECTION_VALIDATION_STAGE,
        progress_percentage=progress_percentage,
        error_code=error_code,
        error_message=message,
    )


def run_discovery_background(
    discovery_run_id: UUID | str,
    settings: Settings,
) -> None:
    """
    Execute one Discovery run outside the HTTP request cycle.

    The source-database password is decrypted from PostgreSQL using
    the local source-credential encryption key.

    Azure Key Vault is retained only for retrieving the OpenAI key
    required by the Classification and HIPAA agents.
    """

    run_id = str(discovery_run_id)

    database = MetadataDatabase(settings)
    repository = DiscoveryRepository(database)
    key_vault = KeyVaultService(settings)

    source_connector = None
    password: str | None = None

    try:
        # ========================================================
        # Load Discovery run
        # ========================================================

        run = repository.get_run(run_id)

        if run is None:
            logger.error(
                "Discovery run was not found",
                extra={
                    "discovery_run_id": run_id,
                },
            )
            return

        # ========================================================
        # Load saved datasource metadata
        # ========================================================

        datasource = repository.get_datasource_for_run(
            run_id
        )

        if datasource is None:
            _fail_connection_validation(
                repository=repository,
                run_id=run_id,
                error_code="DATASOURCE_NOT_FOUND",
                message=(
                    "Datasource connection was not found."
                ),
            )
            return

        if not datasource.get("is_active", False):
            _fail_connection_validation(
                repository=repository,
                run_id=run_id,
                error_code="DATASOURCE_INACTIVE",
                message=(
                    "Datasource connection is inactive."
                ),
            )
            return

        # ========================================================
        # Decrypt source-database password
        # ========================================================

        try:
            encryption_key = (
                settings
                .source_credential_encryption_key
                .get_secret_value()
            )

            password = repository.get_datasource_password(
                connection_id=(
                    datasource["connection_id"]
                ),
                encryption_key=encryption_key,
            )

        except Exception as error:
            _fail_connection_validation(
                repository=repository,
                run_id=run_id,
                error_code=(
                    "DATASOURCE_PASSWORD_DECRYPTION_FAILED"
                ),
                message=(
                    "The encrypted datasource password "
                    "could not be decrypted. "
                    f"Failure type: "
                    f"{error.__class__.__name__}."
                ),
            )
            return

        if not password:
            _fail_connection_validation(
                repository=repository,
                run_id=run_id,
                error_code="DATASOURCE_PASSWORD_MISSING",
                message=(
                    "The encrypted datasource password "
                    "is unavailable."
                ),
            )
            return

        # ========================================================
        # Start Connection Validation
        # ========================================================

        repository.update_stage(
            run_id=run_id,
            stage_name=CONNECTION_VALIDATION_STAGE,
            stage_status="RUNNING",
            message="Connecting to datasource",
            processed_items=0,
            total_items=1,
            error_code=None,
            error_message=None,
        )

        repository.update_run_status(
            run_id=run_id,
            status="RUNNING",
            current_stage=CONNECTION_VALIDATION_STAGE,
            progress_percentage=2,
            error_code=None,
            error_message=None,
        )

        # ========================================================
        # Build non-secret connector configuration
        # ========================================================

        safe_config = {
            "host": datasource["host"],
            "port": datasource["port"],
            "database_name": datasource[
                "database_name"
            ],
            "username": datasource["username"],
            "ssl_enabled": datasource[
                "ssl_enabled"
            ],
        }

        schema_name = datasource.get("schema_name")

        if schema_name:
            safe_config["schema_name"] = schema_name

        # ========================================================
        # Validate database type
        # ========================================================

        try:
            database_type = DatabaseType(
                datasource["database_type"]
            )

        except ValueError:
            _fail_connection_validation(
                repository=repository,
                run_id=run_id,
                error_code="UNSUPPORTED_DATABASE_TYPE",
                message=(
                    "The configured datasource type "
                    "is unsupported."
                ),
                progress_percentage=2,
            )
            return

        # ========================================================
        # Open source-database connection
        # ========================================================

        try:
            source_connector = open_source_connector(
                database_type=database_type,
                safe_config=safe_config,
                password=password,
            )

        except Exception as error:
            _fail_connection_validation(
                repository=repository,
                run_id=run_id,
                error_code=(
                    "DATASOURCE_CONNECTION_FAILED"
                ),
                message=(
                    "The datasource connection failed. "
                    f"Failure type: "
                    f"{error.__class__.__name__}."
                ),
                progress_percentage=2,
            )
            return

        # ========================================================
        # Complete Connection Validation
        # ========================================================

        repository.update_stage(
            run_id=run_id,
            stage_name=CONNECTION_VALIDATION_STAGE,
            stage_status="COMPLETED",
            message="Datasource connection successful",
            processed_items=1,
            total_items=1,
            error_code=None,
            error_message=None,
        )

        repository.update_run_status(
            run_id=run_id,
            status="RUNNING",
            current_stage=CONNECTION_VALIDATION_STAGE,
            progress_percentage=8,
            error_code=None,
            error_message=None,
        )

        # ========================================================
        # Create Discovery components
        # ========================================================

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

        # ========================================================
        # Create LangGraph supervisor
        # ========================================================

        supervisor = DiscoverySupervisor(
            metadata_agent=metadata_agent,
            classification_agent=(
                classification_agent
            ),
            dependency_agent=dependency_agent,
            hipaa_agent=hipaa_agent,
            report_agent=report_agent,
            repository=repository,
            settings=settings,
            key_vault=key_vault,
        )

        # ========================================================
        # Load run configuration
        # ========================================================

        requested_scopes = list(
            run.get("requested_scopes") or []
        )

        effective_scopes = list(
            run.get("effective_scopes")
            or requested_scopes
        )

        selected_objects = list(
            run.get("selected_objects") or []
        )

        selected_frameworks = list(
            run.get("selected_frameworks") or []
        )

        # ========================================================
        # Validate the selected object configuration
        # ========================================================

        invalid_selected_objects = [
            selected_object
            for selected_object in selected_objects
            if not isinstance(selected_object, dict)
            or not selected_object.get("object_name")
            or not selected_object.get("object_type")
        ]

        if invalid_selected_objects:
            raise ValueError(
                "One or more selected objects do not contain "
                "object_name and object_type."
            )

        # ========================================================
        # Log non-secret workflow configuration
        # ========================================================

        logger.info(
            "Starting Discovery supervisor",
            extra={
                "discovery_run_id": run_id,
                "connection_id": (
                    datasource["connection_id"]
                ),
                "requested_scopes": requested_scopes,
                "effective_scopes": effective_scopes,
                "selected_object_count": len(
                    selected_objects
                ),
                "selected_objects": [
                    {
                        "object_name": (
                            selected_object.get(
                                "object_name"
                            )
                        ),
                        "object_type": (
                            selected_object.get(
                                "object_type"
                            )
                        ),
                    }
                    for selected_object
                    in selected_objects
                ],
                "selected_framework_count": len(
                    selected_frameworks
                ),
                "selected_frameworks": (
                    selected_frameworks
                ),
            },
        )

        # ========================================================
        # Execute Discovery workflow
        # ========================================================

        workflow_started_at = perf_counter()

        try:
            supervisor.invoke(
                discovery_run_id=run_id,
                connection_id=datasource[
                    "connection_id"
                ],
                scopes=effective_scopes,
                source_connection=source_connector,
                selected_objects=selected_objects,
                selected_frameworks=(
                    selected_frameworks
                ),
            )

        finally:
            workflow_duration_seconds = round(
                perf_counter()
                - workflow_started_at,
                3,
            )

            logger.info(
                "Discovery supervisor execution finished",
                extra={
                    "discovery_run_id": run_id,
                    "workflow_duration_seconds": (
                        workflow_duration_seconds
                    ),
                    "selected_object_count": len(
                        selected_objects
                    ),
                    "selected_framework_count": len(
                        selected_frameworks
                    ),
                },
            )

        # ========================================================
        # Mark report finalization as completed
        # ========================================================

        repository.update_stage(
            run_id=run_id,
            stage_name="REPORT_FINALIZATION",
            stage_status="COMPLETED",
            message="Discovery run completed",
            processed_items=1,
            total_items=1,
            error_code=None,
            error_message=None,
        )

        # ========================================================
        # Mark overall run as succeeded
        # ========================================================

        repository.update_run_status(
            run_id=run_id,
            status="SUCCEEDED",
            current_stage="REPORT_FINALIZATION",
            progress_percentage=100.0,
            error_code=None,
            error_message=None,
        )

    except Exception as error:
        logger.exception(
            "Discovery run failed: %s",
            error,
            extra={
                "discovery_run_id": run_id,
            },
        )

        error_message = str(error)
        current = None

        try:
            current = repository.get_run(run_id)

        except Exception:
            logger.error(
                (
                    "Could not reload discovery run "
                    "after task failure"
                ),
                exc_info=True,
                extra={
                    "discovery_run_id": run_id,
                },
            )

        current_stage = (
            current.get("current_stage")
            if current
            else None
        )

        progress_percentage = (
            current.get("progress_percentage")
            if current
            else None
        )

        try:
            if current_stage:
                repository.update_stage(
                    run_id=run_id,
                    stage_name=current_stage,
                    stage_status="FAILED",
                    message="Discovery run failed",
                    error_code="DISCOVERY_RUN_FAILED",
                    error_message=error_message,
                )

            repository.update_run_status(
                run_id=run_id,
                status="FAILED",
                current_stage=current_stage,
                progress_percentage=(
                    progress_percentage
                ),
                error_code="DISCOVERY_RUN_FAILED",
                error_message=error_message,
            )

        except Exception:
            logger.error(
                (
                    "Could not persist Discovery run "
                    "failure status"
                ),
                exc_info=True,
                extra={
                    "discovery_run_id": run_id,
                },
            )

    finally:
        # ========================================================
        # Close source connector
        # ========================================================

        if source_connector is not None:
            try:
                source_connector.close()

            except Exception:
                logger.warning(
                    "Source connector cleanup failed",
                    extra={
                        "discovery_run_id": run_id,
                    },
                )

        # Remove the local reference to the decrypted password.
        password = None

        # ========================================================
        # Close Key Vault client
        # ========================================================

        try:
            key_vault.close()

        except Exception:
            logger.warning(
                "Key Vault client cleanup failed",
                extra={
                    "discovery_run_id": run_id,
                },
            )

        # ========================================================
        # Dispose background-job database engine
        # ========================================================

        try:
            database.dispose()

        except AttributeError:
            # The database service may not yet contain dispose().
            pass

        except Exception:
            logger.warning(
                (
                    "Metadata database cleanup "
                    "failed"
                ),
                extra={
                    "discovery_run_id": run_id,
                },
            )