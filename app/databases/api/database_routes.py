"""Database lifecycle HTTP endpoints.

Exposes provisioning, inspection, credential retrieval, and TTL-driven
pause/resume actions for the databases owned by the authenticated user. All
business rules (storage quotas, connection limits, TTL policy) are enforced
by the underlying Stored Procedures; this module only mediates HTTP <-> SQL.
"""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from app.auth.dependencies.auth_dependencies import get_current_user
from app.auth.schemas.auth_schemas import AuthenticatedUser
from app.databases.repositories.database_repository import DatabaseManagementRepository
from app.databases.schemas.database_schemas import (
    CreateDatabaseRequest,
    DatabaseActionResponse,
    DatabaseCredentials,
    DatabaseInstance,
    DatabaseListResponse,
    DatabaseStatus,
    DatabaseUsage,
)
from app.databases.services.database_service import DatabaseService
from app.repositories.exceptions.database_exceptions import (
    DatabaseIntegrationError,
    ResourceNotFoundError,
)

router = APIRouter(prefix="/databases", tags=["Databases"])
logger = logging.getLogger(__name__)


def get_database_service() -> DatabaseService:
    """Return the Stored Procedure-backed database service dependency."""

    return DatabaseService(repository=DatabaseManagementRepository())


CurrentUser = Annotated[AuthenticatedUser, Depends(get_current_user)]
Service = Annotated[DatabaseService, Depends(get_database_service)]


def _unavailable(exc: Exception) -> HTTPException:
    logger.error("Database service call failed", exc_info=exc)
    return HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="Database service unavailable",
    )


@router.post(
    "",
    response_model=DatabaseActionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Provision a new database instance",
    description=(
        "Provision an additional database instance for the authenticated "
        "user. Storage quotas and per-user provisioning limits are enforced "
        "by the database layer."
    ),
)
def create_database(
    current_user: CurrentUser,
    service: Service,
    _request: CreateDatabaseRequest | None = None,
) -> DatabaseActionResponse:
    """Provision a new database instance for the authenticated user."""

    try:
        service.provision_database(current_user.subject)
    except DatabaseIntegrationError as exc:
        raise _unavailable(exc) from exc

    return DatabaseActionResponse(
        database_id=current_user.subject,
        status=DatabaseStatus.ACTIVE,
        detail="Database provisioning requested",
    )


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
        return service.get_database(current_user.subject, database_id)
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
    database_id: str,
    current_user: CurrentUser,
    service: Service,
) -> DatabaseActionResponse:
    """Deprovision a database instance owned by the authenticated user."""

    try:
        return service.delete_database(current_user.subject, database_id)
    except DatabaseIntegrationError as exc:
        raise _unavailable(exc) from exc


@router.get(
    "/{database_id}/credentials",
    response_model=DatabaseCredentials,
    summary="Retrieve connection credentials",
    description=(
        "Return the connection credentials for the authenticated user's "
        "database. Previously implemented at the repository layer but never "
        "exposed over HTTP."
    ),
)
def get_database_credentials(
    database_id: str,
    current_user: CurrentUser,
    service: Service,
) -> DatabaseCredentials:
    """Return connection credentials for the authenticated user's database."""

    try:
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
    database_id: str,
    current_user: CurrentUser,
    service: Service,
) -> DatabaseActionResponse:
    """Pause a database instance owned by the authenticated user."""

    try:
        return service.pause_database(current_user.subject, database_id)
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
        return service.resume_database(current_user.subject, database_id)
    except DatabaseIntegrationError as exc:
        raise _unavailable(exc) from exc
