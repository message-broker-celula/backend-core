"""Audit HTTP endpoints."""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.audit.repositories.audit_repository import AuditRepository
from app.audit.schemas.audit_schemas import AuditEventResponse, RegisterAuditEventRequest
from app.audit.services.audit_service import AuditService
from app.auth.dependencies.auth_dependencies import get_current_user
from app.auth.schemas.auth_schemas import AuthenticatedUser
from app.repositories.exceptions.database_exceptions import (
    BusinessRuleViolationError,
    DatabaseIntegrationError,
)

router = APIRouter(prefix="/audit", tags=["Audit"])
logger = logging.getLogger(__name__)


def get_audit_service() -> AuditService:
    """Return the Stored Procedure-backed audit service dependency."""

    return AuditService(repository=AuditRepository())


CurrentUser = Annotated[AuthenticatedUser, Depends(get_current_user)]
Service = Annotated[AuditService, Depends(get_audit_service)]


@router.post(
    "/events",
    response_model=AuditEventResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a generic audit event",
)
def register_audit_event(
    request: Request,
    payload: RegisterAuditEventRequest,
    current_user: CurrentUser,
    service: Service,
) -> AuditEventResponse:
    """Call sp_RegistrarEvento for generic application events."""

    try:
        service.register_event(
            event=payload.evento,
            subject=current_user.subject,
            database_id=payload.id_bd,
            description=payload.descripcion,
            ip=request.client.host if request.client else None,
            result=payload.resultado,
            additional_data=payload.datos_adicionales,
        )
    except BusinessRuleViolationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=exc.detail) from exc
    except DatabaseIntegrationError as exc:
        logger.error("Audit event registration failed", exc_info=exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Audit service unavailable",
        ) from exc
    return AuditEventResponse()
