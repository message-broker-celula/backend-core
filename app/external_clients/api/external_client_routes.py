"""Public, machine-to-machine PostgreSQL provisioning endpoints.

Lets another team's own backend register itself and provision real
PostgreSQL databases without a human OAuth login -- mirroring how this
backend consumes the Ollama Gateway's own `/public/clients/register` ->
API key -> Bearer auth contract.

Registration creates a "shadow" `Usuarios` row (see
`ExternalClientService`/`sp_RegistrarClienteExterno`) so every database
lifecycle operation below reuses `DatabaseService` completely unmodified --
the exact same quota (5 active databases), encryption, and provisioning
code already verified live for the JWT-authenticated `/databases` routes.
"""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.auth.schemas.auth_schemas import AuthenticatedUser
from app.core.rate_limit import limiter
from app.databases.api.database_routes import get_database_service
from app.databases.schemas.database_schemas import (
    DatabaseActionResponse,
    DatabaseCredentials,
    DatabaseListResponse,
    DatabaseStatus,
)
from app.databases.services.database_service import DatabaseService
from app.external_clients.dependencies import (
    get_current_external_client,
    get_external_client_service,
)
from app.external_clients.schemas.external_client_schemas import (
    CreateExternalDatabaseRequest,
    ExternalClientActionResponse,
    ExternalClientKeyResponse,
    ExternalClientMetricsResponse,
    RegisterExternalClientRequest,
)
from app.external_clients.services.external_client_service import ExternalClientService
from app.repositories.exceptions.database_exceptions import (
    BusinessRuleViolationError,
    DatabaseIntegrationError,
    ResourceNotFoundError,
)

router = APIRouter(prefix="/public/postgres", tags=["PostgreSQL for external teams"])
logger = logging.getLogger(__name__)

ExternalClient = Annotated[AuthenticatedUser, Depends(get_current_external_client)]
ClientService = Annotated[ExternalClientService, Depends(get_external_client_service)]
DbService = Annotated[DatabaseService, Depends(get_database_service)]


def _unavailable(exc: Exception) -> HTTPException:
    logger.error("External Postgres service call failed", exc_info=exc)
    return HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="PostgreSQL provisioning service unavailable",
    )


def _business_error(exc: BusinessRuleViolationError) -> HTTPException:
    return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=exc.detail)


def _bearer_token(request: Request) -> str:
    header = request.headers.get("authorization", "")
    if not header.lower().startswith("bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing bearer API key")
    return header[len("bearer ") :].strip()


@router.post(
    "/register",
    response_model=ExternalClientKeyResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register an external team and receive a Postgres API key",
)
@limiter.limit("5/minute")
def register_external_client(
    request: Request,
    payload: RegisterExternalClientRequest,
    service: ClientService,
) -> ExternalClientKeyResponse:
    """Self-service registration -- no auth required, mirrors the AI Gateway's own contract."""

    try:
        return service.register(
            payload.team_name,
            payload.contact_email,
            request.client.host if request.client else None,
        )
    except BusinessRuleViolationError as exc:
        raise _business_error(exc) from exc
    except DatabaseIntegrationError as exc:
        raise _unavailable(exc) from exc


@router.post(
    "/api-key/rotate",
    response_model=ExternalClientKeyResponse,
    summary="Rotate the caller's own API key",
)
def rotate_api_key(request: Request, service: ClientService) -> ExternalClientKeyResponse:
    """Invalidate the current key immediately and issue a new one."""

    try:
        return service.rotate(_bearer_token(request), request.client.host if request.client else None)
    except DatabaseIntegrationError as exc:
        raise _unavailable(exc) from exc


@router.delete(
    "/api-key",
    response_model=ExternalClientActionResponse,
    summary="Revoke the caller's own API key",
)
def revoke_api_key(request: Request, service: ClientService) -> ExternalClientActionResponse:
    """Revoke the current key -- the caller will need to register again to get a new one."""

    try:
        service.revoke(_bearer_token(request), request.client.host if request.client else None)
    except DatabaseIntegrationError as exc:
        raise _unavailable(exc) from exc
    return ExternalClientActionResponse(detail="API key revoked")


@router.get(
    "/databases",
    response_model=DatabaseListResponse,
    summary="List the caller's own PostgreSQL databases",
)
def list_external_databases(current_client: ExternalClient, service: DbService) -> DatabaseListResponse:
    try:
        databases = service.list_databases(current_client.subject)
    except DatabaseIntegrationError as exc:
        raise _unavailable(exc) from exc
    return DatabaseListResponse(databases=databases)


@router.get(
    "/metrics",
    response_model=ExternalClientMetricsResponse,
    summary="Aggregate usage metrics for the caller's own PostgreSQL databases",
)
def get_external_metrics(current_client: ExternalClient, service: DbService) -> ExternalClientMetricsResponse:
    """Scoped strictly to the caller -- no visibility into other clients' databases."""

    try:
        databases = service.list_databases(current_client.subject)
    except DatabaseIntegrationError as exc:
        raise _unavailable(exc) from exc

    return ExternalClientMetricsResponse(
        total_databases=len(databases),
        active_databases=sum(1 for db in databases if db.status == DatabaseStatus.ACTIVE),
        storage_used_mb=sum(db.storage_used_mb or 0 for db in databases),
        storage_limit_mb=sum(db.storage_limit_mb or 0 for db in databases),
    )


@router.post(
    "/databases",
    response_model=DatabaseActionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Provision a new PostgreSQL database for the caller",
)
def create_external_database(
    request: Request,
    payload: CreateExternalDatabaseRequest,
    current_client: ExternalClient,
    service: DbService,
) -> DatabaseActionResponse:
    """Always provisions PostgreSQL -- the engine is fixed server-side, never client-chosen."""

    try:
        engines = service.list_available_engines()
    except DatabaseIntegrationError as exc:
        raise _unavailable(exc) from exc

    postgres = next((engine for engine in engines if engine.nombre_motor == "POSTGRES"), None)
    if postgres is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="PostgreSQL provisioning is not currently available",
        )

    try:
        return service.create_database(
            current_client.subject,
            {
                "nombre_motor": "POSTGRES",
                "version_motor": postgres.version_motor,
                "nombre_bd": payload.nombre_bd,
                "espacio_maximo_mb": 20,
                "conexiones_maximas": 5,
                "ttl_dias": 30,
                "id_celula": None,
            },
            request.client.host if request.client else None,
        )
    except BusinessRuleViolationError as exc:
        raise _business_error(exc) from exc
    except DatabaseIntegrationError as exc:
        raise _unavailable(exc) from exc


@router.get(
    "/databases/{database_id}/credentials",
    response_model=DatabaseCredentials,
    summary="Retrieve connection credentials for the caller's own database",
)
def get_external_database_credentials(
    database_id: str,
    current_client: ExternalClient,
    service: DbService,
) -> DatabaseCredentials:
    try:
        # Ownership check (raises ResourceNotFoundError for someone else's
        # database_id) must happen before register_activity, which has no
        # subject/ownership check of its own -- same order database_routes.py
        # uses via its _touch_database helper.
        service.get_database(current_client.subject, database_id)
        service.register_activity(database_id)
        return service.get_credentials(current_client.subject, database_id)
    except ResourceNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Database credentials not found",
        ) from exc
    except DatabaseIntegrationError as exc:
        raise _unavailable(exc) from exc


@router.delete(
    "/databases/{database_id}",
    response_model=DatabaseActionResponse,
    summary="Deprovision the caller's own database",
)
def delete_external_database(
    request: Request,
    database_id: str,
    current_client: ExternalClient,
    service: DbService,
) -> DatabaseActionResponse:
    try:
        service.get_database(current_client.subject, database_id)
        return service.delete_database(
            current_client.subject,
            database_id,
            request.client.host if request.client else None,
        )
    except ResourceNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Database not found") from exc
    except BusinessRuleViolationError as exc:
        raise _business_error(exc) from exc
    except DatabaseIntegrationError as exc:
        raise _unavailable(exc) from exc
