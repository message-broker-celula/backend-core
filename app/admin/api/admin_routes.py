"""Administration HTTP endpoints.

Restricted to the "admin" role via the `require_role` authorization
dependency (defense-in-depth: the underlying Stored Procedures also
validate the ADMIN role themselves inside SQL Server). Provides oversight
over registered users, role assignment, and a global view of every
provisioned database.
"""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status

from app.admin.repositories.admin_repository import AdminRepository
from app.admin.schemas.admin_schemas import (
    AdminDatabaseListResponse,
    AdminUserListResponse,
    AdminUserSummary,
    UpdateUserRoleRequest,
)
from app.admin.services.admin_service import AdminService
from app.auth.dependencies.auth_dependencies import require_role
from app.auth.schemas.auth_schemas import AuthenticatedUser
from app.repositories.exceptions.database_exceptions import (
    BusinessRuleViolationError,
    DatabaseIntegrationError,
)

router = APIRouter(prefix="/admin", tags=["Administration"])
logger = logging.getLogger(__name__)


def get_admin_service() -> AdminService:
    """Return the Stored Procedure-backed administration service dependency."""

    return AdminService(repository=AdminRepository())


RequireAdmin = Annotated[AuthenticatedUser, Depends(require_role("admin"))]
Service = Annotated[AdminService, Depends(get_admin_service)]


def _unavailable(exc: Exception) -> HTTPException:
    logger.error("Admin service call failed", exc_info=exc)
    return HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="Administration service unavailable",
    )


@router.get(
    "/users",
    response_model=AdminUserListResponse,
    summary="List all registered users",
    description="Requires the 'admin' role.",
)
def list_users(
    admin: RequireAdmin,
    service: Service,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
) -> AdminUserListResponse:
    """List all registered users for administrative oversight."""

    try:
        return AdminUserListResponse(
            users=service.list_users(admin.subject, page, page_size)
        )
    except BusinessRuleViolationError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=exc.detail) from exc
    except DatabaseIntegrationError as exc:
        raise _unavailable(exc) from exc


@router.patch(
    "/users/{user_id}/role",
    response_model=AdminUserSummary,
    summary="Update a user's role",
    description="Requires the 'admin' role.",
)
def update_user_role(
    request: Request,
    user_id: str,
    payload: UpdateUserRoleRequest,
    admin: RequireAdmin,
    service: Service,
) -> AdminUserSummary:
    """Update the role assigned to a user."""

    try:
        return service.update_user_role(
            admin.subject,
            user_id,
            payload.role,
            request.client.host if request.client else None,
        )
    except BusinessRuleViolationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=exc.detail) from exc
    except DatabaseIntegrationError as exc:
        raise _unavailable(exc) from exc


@router.get(
    "/databases",
    response_model=AdminDatabaseListResponse,
    summary="List every provisioned database",
    description=(
        "Global oversight view across all users' databases. Requires the "
        "'admin' role."
    ),
)
def list_all_databases(
    admin: RequireAdmin,
    service: Service,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    status_filter: str | None = Query(default=None, pattern="^(ACTIVA|PAUSADA|ELIMINADA)$"),
) -> AdminDatabaseListResponse:
    """List every provisioned database across all users."""

    try:
        return AdminDatabaseListResponse(
            databases=service.list_all_databases(
                admin.subject,
                page,
                page_size,
                status_filter,
            )
        )
    except BusinessRuleViolationError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=exc.detail) from exc
    except DatabaseIntegrationError as exc:
        raise _unavailable(exc) from exc
