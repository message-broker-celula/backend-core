"""Célula (team workspace) HTTP endpoints.

Exposes creation and listing of célula workspaces, plus registration of the
subdomain-backed services under each célula, per the addressing scheme:
`https://[celula].andrescortes.dev` and
`https://[servicio].[celula].andrescortes.dev`.
"""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.auth.dependencies.auth_dependencies import get_current_user
from app.auth.schemas.auth_schemas import AuthenticatedUser
from app.celulas.repositories.celula_repository import CelulaRepository
from app.celulas.schemas.celula_schemas import (
    Celula,
    CelulaListResponse,
    CelulaService,
    CelulaServiceListResponse,
    ChangeServiceStatusRequest,
    CreateCelulaRequest,
    RegisterCelulaServiceRequest,
)
from app.celulas.services.celula_service import CelulaOrchestrationService
from app.repositories.exceptions.database_exceptions import (
    DatabaseIntegrationError,
    ResourceNotFoundError,
)

router = APIRouter(prefix="/celulas", tags=["Células"])
logger = logging.getLogger(__name__)


def get_celula_service() -> CelulaOrchestrationService:
    """Return the Stored Procedure-backed célula service dependency."""

    return CelulaOrchestrationService(repository=CelulaRepository())


CurrentUser = Annotated[AuthenticatedUser, Depends(get_current_user)]
Service = Annotated[CelulaOrchestrationService, Depends(get_celula_service)]


def _unavailable(exc: Exception) -> HTTPException:
    logger.error("Célula service call failed", exc_info=exc)
    return HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="Célula service unavailable",
    )


@router.post(
    "",
    response_model=Celula,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new célula workspace",
)
def create_celula(
    request: Request,
    payload: CreateCelulaRequest,
    current_user: CurrentUser,
    service: Service,
) -> Celula:
    """Create a new célula workspace owned by the authenticated user."""

    try:
        return service.create_celula(
            current_user.subject,
            payload.name,
            request.client.host if request.client else None,
        )
    except DatabaseIntegrationError as exc:
        raise _unavailable(exc) from exc


@router.get(
    "",
    response_model=CelulaListResponse,
    summary="List célula workspaces",
)
def list_celulas(current_user: CurrentUser, service: Service) -> CelulaListResponse:
    """List célula workspaces visible to the authenticated user."""

    try:
        return CelulaListResponse(celulas=service.list_celulas(current_user.subject))
    except DatabaseIntegrationError as exc:
        raise _unavailable(exc) from exc


@router.get(
    "/{celula_id}",
    response_model=Celula,
    summary="Get a single célula workspace",
    responses={404: {"description": "Célula not found"}},
)
def get_celula(
    celula_id: str,
    current_user: CurrentUser,
    service: Service,
) -> Celula:
    """Fetch a single célula workspace scoped to the authenticated user."""

    try:
        return service.get_celula(current_user.subject, celula_id)
    except ResourceNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Célula not found",
        ) from exc
    except DatabaseIntegrationError as exc:
        raise _unavailable(exc) from exc


@router.post(
    "/{celula_id}/services",
    response_model=CelulaService,
    status_code=status.HTTP_201_CREATED,
    summary="Register a subdomain-backed service under a célula",
)
def register_celula_service(
    request: Request,
    celula_id: str,
    payload: RegisterCelulaServiceRequest,
    current_user: CurrentUser,
    service: Service,
) -> CelulaService:
    """Register a new service (frontend/api/etc.) under a célula."""

    try:
        return service.register_service(
            subject=current_user.subject,
            celula_id=celula_id,
            service_name=payload.service_name,
            service_type=payload.service_type,
            database_id=payload.database_id,
            port=payload.puerto_interno,
            ip=request.client.host if request.client else None,
        )
    except DatabaseIntegrationError as exc:
        raise _unavailable(exc) from exc


@router.get(
    "/{celula_id}/services",
    response_model=CelulaServiceListResponse,
    summary="List services registered under a célula",
)
def list_celula_services(
    celula_id: str,
    current_user: CurrentUser,
    service: Service,
) -> CelulaServiceListResponse:
    """List every service registered under a célula."""

    try:
        return CelulaServiceListResponse(
            services=service.list_services(current_user.subject, celula_id)
        )
    except DatabaseIntegrationError as exc:
        raise _unavailable(exc) from exc


@router.delete(
    "/{celula_id}/services/{service_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Remove a service registered under a célula",
)
def delete_celula_service(
    celula_id: str,
    service_id: str,
    current_user: CurrentUser,
    service: Service,
) -> None:
    """Remove a service registered under a célula."""

    try:
        service.delete_service(current_user.subject, celula_id, service_id)
    except DatabaseIntegrationError as exc:
        raise _unavailable(exc) from exc


@router.patch(
    "/services/{service_id}/estado",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Change a registered service status",
)
def change_service_status(
    request: Request,
    service_id: str,
    payload: ChangeServiceStatusRequest,
    current_user: CurrentUser,
    service: Service,
) -> None:
    """Call sp_CambiarEstadoServicio."""

    try:
        service.change_service_status(
            current_user.subject,
            service_id,
            payload.nuevo_estado,
            request.client.host if request.client else None,
        )
    except DatabaseIntegrationError as exc:
        raise _unavailable(exc) from exc
