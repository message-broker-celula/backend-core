"""Administration HTTP endpoints.

Restricted to the "admin" role via the existing `require_role` authorization
dependency (previously defined but never wired to any route). Provides
oversight over registered users, role assignment, and a global view of every
provisioned database.
"""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

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
from app.repositories.exceptions.database_exceptions import DatabaseIntegrationError

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
def list_users(_admin: RequireAdmin, service: Service) -> AdminUserListResponse:
    """List all registered users for administrative oversight."""

    try:
        return AdminUserListResponse(users=service.list_users())
    except DatabaseIntegrationError as exc:
        raise _unavailable(exc) from exc


@router.patch(
    "/users/{user_id}/role",
    response_model=AdminUserSummary,
    summary="Update a user's role",
    description="Requires the 'admin' role.",
)
def update_user_role(
    user_id: str,
    payload: UpdateUserRoleRequest,
    _admin: RequireAdmin,
    service: Service,
) -> AdminUserSummary:
    """Update the role assigned to a user."""

    try:
        return service.update_user_role(user_id, payload.role)
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
def list_all_databases(_admin: RequireAdmin, service: Service) -> AdminDatabaseListResponse:
    """List every provisioned database across all users."""

    try:
        return AdminDatabaseListResponse(databases=service.list_all_databases())
    except DatabaseIntegrationError as exc:
        raise _unavailable(exc) from exc
