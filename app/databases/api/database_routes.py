"""Database lifecycle HTTP endpoints.

Exposes provisioning, inspection, credential retrieval, and TTL-driven
pause/resume actions for the databases owned by the authenticated user. All
business rules (storage quotas, connection limits, TTL policy) are enforced
by the underlying Stored Procedures; this module only mediates HTTP <-> SQL.
"""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.auth.dependencies.auth_dependencies import get_current_user
from app.auth.schemas.auth_schemas import AuthenticatedUser
from app.core.config import settings
from app.databases.repositories.database_repository import DatabaseManagementRepository
from app.databases.schemas.database_schemas import (
    CreateDatabaseRequest,
    DatabaseActionResponse,
    DatabaseCredentials,
    DatabaseInstance,
    DatabaseListResponse,
    DatabaseUsage,
    DaysRemainingResponse,
    SpacePercentageResponse,
    UpdateDatabaseSpaceRequest,
    UpdateDatabaseSpaceResponse,
    ValidateConnectionResponse,
)
from app.databases.services.database_service import DatabaseService
from app.provisioning.clients.http_provisioner_client import HttpProvisionerClient
from app.provisioning.port_allocator import PortAllocator
from app.provisioning.services.provisioning_service import DatabaseProvisioningService
from app.repositories.exceptions.database_exceptions import (
    BusinessRuleViolationError,
    DatabaseIntegrationError,
    ResourceNotFoundError,
)

router = APIRouter(prefix="/databases", tags=["Databases"])
logger = logging.getLogger(__name__)


def get_database_service() -> DatabaseService:
    """Return the Stored Procedure-backed database service dependency."""

    repository = DatabaseManagementRepository()
    provisioning_settings = settings.provisioning
    client = HttpProvisionerClient(
        base_url=provisioning_settings.base_url,
        shared_secret=provisioning_settings.shared_secret.get_secret_value(),
        timeout=provisioning_settings.request_timeout_seconds,
    )
    allocator = PortAllocator(
        port_repository=repository,
        range_start=provisioning_settings.port_range_start,
        range_end=provisioning_settings.port_range_end,
    )
    provisioning = DatabaseProvisioningService(
        client=client,
        port_allocator=allocator,
        public_host=provisioning_settings.public_host,
        supported_engines=provisioning_settings.supported_engines,
        password_length=provisioning_settings.password_length,
        port_allocation_attempts=provisioning_settings.port_allocation_attempts,
    )
    return DatabaseService(repository=repository, provisioning=provisioning)


CurrentUser = Annotated[AuthenticatedUser, Depends(get_current_user)]
Service = Annotated[DatabaseService, Depends(get_database_service)]


def _unavailable(exc: Exception) -> HTTPException:
    logger.error("Database service call failed", exc_info=exc)
    return HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="Database service unavailable",
    )


def _business_error(exc: BusinessRuleViolationError) -> HTTPException:
    return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=exc.detail)


def _touch_database(
    service: DatabaseService,
    subject: str,
    database_id: str,
    ttl_days: int = 30,
) -> None:
    """Validate ownership and refresh the database activity TTL.

    Per the backend guide: sp_RegistrarActividad must be called on every
    request that touches a user's database, or the TTL cleanup job will
    pause it for looking inactive.
    """

    service.get_database(subject, database_id)
    service.register_activity(database_id, ttl_days)


@router.post(
    "",
    response_model=DatabaseActionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Provision a new database instance",
)
def create_database(
    request: Request,
    current_user: CurrentUser,
    service: Service,
    # Default instance, not just default fields: the landing app's
    # post-login auto-provisioning call sends a completely empty body (no
    # engine/version/name picker in the UI) -- FastAPI requires the body
    # *parameter itself* to have a default before an empty request body is
    # accepted at all, field-level defaults on CreateDatabaseRequest alone
    # are not enough (confirmed: an empty body 422s on "body: Field
    # required" before Pydantic ever gets to apply its own field defaults).
    payload: CreateDatabaseRequest = CreateDatabaseRequest(),
) -> DatabaseActionResponse:
    """Provision a new database instance for the authenticated user."""

    try:
        return service.create_database(
            current_user.subject,
            payload.model_dump(),
            request.client.host if request.client else None,
        )
    except BusinessRuleViolationError as exc:
        raise _business_error(exc) from exc
    except DatabaseIntegrationError as exc:
        raise _unavailable(exc) from exc


@router.get(
    "",
    response_model=DatabaseListResponse,
    summary="List the authenticated user's databases",
)
def list_databases(current_user: CurrentUser, service: Service) -> DatabaseListResponse:
    """List every database instance owned by the authenticated user."""

    try:
        databases = service.list_databases(current_user.subject)
    except DatabaseIntegrationError as exc:
        raise _unavailable(exc) from exc

    return DatabaseListResponse(databases=databases)


@router.get(
    "/{database_id}",
    response_model=DatabaseInstance,
    summary="Get a single database instance",
    responses={404: {"description": "Database not found"}},
)
def get_database(
    database_id: str,
    current_user: CurrentUser,
    service: Service,
) -> DatabaseInstance:
    """Fetch a single database instance owned by the authenticated user."""

    try:
        database = service.get_database(current_user.subject, database_id)
        service.register_activity(database_id)
        return database
    except ResourceNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Database not found",
        ) from exc
    except DatabaseIntegrationError as exc:
        raise _unavailable(exc) from exc


@router.delete(
    "/{database_id}",
    response_model=DatabaseActionResponse,
    summary="Deprovision a database instance",
)
def delete_database(
    request: Request,
    database_id: str,
    current_user: CurrentUser,
    service: Service,
) -> DatabaseActionResponse:
    """Deprovision a database instance owned by the authenticated user."""

    try:
        _touch_database(service, current_user.subject, database_id)
        return service.delete_database(
            current_user.subject,
            database_id,
            request.client.host if request.client else None,
        )
    except BusinessRuleViolationError as exc:
        raise _business_error(exc) from exc
    except DatabaseIntegrationError as exc:
        raise _unavailable(exc) from exc


@router.get(
    "/{database_id}/credentials",
    response_model=DatabaseCredentials,
    summary="Retrieve connection credentials",
)
def get_database_credentials(
    database_id: str,
    current_user: CurrentUser,
    service: Service,
) -> DatabaseCredentials:
    """Return connection credentials for the authenticated user's database."""

    try:
        _touch_database(service, current_user.subject, database_id)
        return service.get_credentials(current_user.subject, database_id)
    except ResourceNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Database credentials not found",
        ) from exc
    except DatabaseIntegrationError as exc:
        raise _unavailable(exc) from exc


@router.get(
    "/{database_id}/usage",
    response_model=DatabaseUsage,
    summary="Get storage and connection usage",
    responses={404: {"description": "Usage information not found"}},
)
def get_database_usage(
    database_id: str,
    current_user: CurrentUser,
    service: Service,
) -> DatabaseUsage:
    """Fetch storage and connection usage for a database instance."""

    try:
        _touch_database(service, current_user.subject, database_id)
        return service.get_usage(current_user.subject, database_id)
    except ResourceNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Usage information not found",
        ) from exc
    except DatabaseIntegrationError as exc:
        raise _unavailable(exc) from exc


@router.post(
    "/{database_id}/pause",
    response_model=DatabaseActionResponse,
    summary="Pause a database instance",
)
def pause_database(
    request: Request,
    database_id: str,
    current_user: CurrentUser,
    service: Service,
) -> DatabaseActionResponse:
    """Pause a database instance owned by the authenticated user."""

    try:
        _touch_database(service, current_user.subject, database_id)
        return service.pause_database(
            current_user.subject,
            database_id,
            request.client.host if request.client else None,
        )
    except BusinessRuleViolationError as exc:
        raise _business_error(exc) from exc
    except DatabaseIntegrationError as exc:
        raise _unavailable(exc) from exc


@router.post(
    "/{database_id}/resume",
    response_model=DatabaseActionResponse,
    summary="Resume a paused database instance",
)
def resume_database(
    database_id: str,
    current_user: CurrentUser,
    service: Service,
) -> DatabaseActionResponse:
    """Resume a previously paused database instance."""

    try:
        _touch_database(service, current_user.subject, database_id)
        return service.resume_database(current_user.subject, database_id)
    except DatabaseIntegrationError as exc:
        raise _unavailable(exc) from exc


@router.post(
    "/{database_id}/activity",
    response_model=DatabaseActionResponse,
    summary="Register database activity and refresh TTL",
)
def register_database_activity(
    database_id: str,
    current_user: CurrentUser,
    service: Service,
    ttl_days: int = 30,
) -> DatabaseActionResponse:
    """Call sp_RegistrarActividad for a database touched by the user."""

    try:
        service.get_database(current_user.subject, database_id)
        return service.register_activity(database_id, ttl_days)
    except ResourceNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Database not found") from exc
    except BusinessRuleViolationError as exc:
        raise _business_error(exc) from exc
    except DatabaseIntegrationError as exc:
        raise _unavailable(exc) from exc


@router.post(
    "/{database_id}/space",
    response_model=UpdateDatabaseSpaceResponse,
    summary="Report storage usage",
)
def update_database_space(
    request: Request,
    database_id: str,
    payload: UpdateDatabaseSpaceRequest,
    current_user: CurrentUser,
    service: Service,
) -> UpdateDatabaseSpaceResponse:
    """Call sp_ActualizarEspacio after a write operation."""

    try:
        _touch_database(service, current_user.subject, database_id, payload.dias_ttl)
        return service.update_space(
            database_id,
            payload.espacio_reportado_mb,
            request.client.host if request.client else None,
            payload.dias_ttl,
        )
    except ResourceNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Database not found") from exc
    except BusinessRuleViolationError as exc:
        raise _business_error(exc) from exc
    except DatabaseIntegrationError as exc:
        raise _unavailable(exc) from exc


@router.post(
    "/{database_id}/connections/validate",
    response_model=ValidateConnectionResponse,
    summary="Validate a new database connection",
)
def validate_database_connection(
    database_id: str,
    current_user: CurrentUser,
    service: Service,
) -> ValidateConnectionResponse:
    """Call sp_ValidarConexion before opening a user DB connection."""

    try:
        _touch_database(service, current_user.subject, database_id)
        return service.validate_connection(database_id)
    except ResourceNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Database not found") from exc
    except BusinessRuleViolationError as exc:
        raise _business_error(exc) from exc
    except DatabaseIntegrationError as exc:
        raise _unavailable(exc) from exc


@router.post(
    "/{database_id}/connections/release",
    response_model=DatabaseActionResponse,
    summary="Release a database connection",
)
def release_database_connection(
    database_id: str,
    current_user: CurrentUser,
    service: Service,
) -> DatabaseActionResponse:
    """Call sp_LiberarConexion after closing a user DB connection."""

    try:
        _touch_database(service, current_user.subject, database_id)
        return service.release_connection(database_id)
    except ResourceNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Database not found") from exc
    except BusinessRuleViolationError as exc:
        raise _business_error(exc) from exc
    except DatabaseIntegrationError as exc:
        raise _unavailable(exc) from exc


@router.get(
    "/{database_id}/ttl-days",
    response_model=DaysRemainingResponse,
    summary="Get remaining TTL days",
)
def get_ttl_days(
    database_id: str,
    current_user: CurrentUser,
    service: Service,
) -> DaysRemainingResponse:
    """Read fn_DiasRestantesTTL for a user database."""

    try:
        _touch_database(service, current_user.subject, database_id)
        return DaysRemainingResponse(
            database_id=database_id,
            dias_restantes=service.get_ttl_days_remaining(database_id),
        )
    except ResourceNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Database not found") from exc
    except DatabaseIntegrationError as exc:
        raise _unavailable(exc) from exc


@router.get(
    "/{database_id}/space-percentage",
    response_model=SpacePercentageResponse,
    summary="Get storage usage percentage",
)
def get_space_percentage(
    database_id: str,
    current_user: CurrentUser,
    service: Service,
) -> SpacePercentageResponse:
    """Read fn_PorcentajeEspacioUsado for a user database."""

    try:
        _touch_database(service, current_user.subject, database_id)
        return SpacePercentageResponse(
            database_id=database_id,
            porcentaje_usado=service.get_space_percentage(database_id),
        )
    except ResourceNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Database not found") from exc
    except DatabaseIntegrationError as exc:
        raise _unavailable(exc) from exc
