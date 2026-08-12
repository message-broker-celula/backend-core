"""Administration service orchestration.

Maps Stored Procedure results into typed DTOs for administrative endpoints.
No business rules (who can become admin, quota policy, etc.) live here --
those are enforced by the database layer and by the `require_role`
authorization dependency at the HTTP boundary.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any

from app.admin.interfaces.admin_repository import AdminRepositoryProtocol
from app.admin.schemas.admin_schemas import AdminUserSummary
from app.databases.row_mapping import row_to_database_instance
from app.databases.schemas.database_schemas import DatabaseInstance

logger = logging.getLogger(__name__)


class AdminService:
    """Coordinate administrative orchestration for the `/admin` API."""

    def __init__(self, repository: AdminRepositoryProtocol) -> None:
        """Initialize the service with an administration repository."""

        self._repository = repository

    def list_users(
        self,
        requester_id: str,
        page: int = 1,
        page_size: int = 50,
    ) -> list[AdminUserSummary]:
        """List all registered users."""

        rows = self._repository.list_users(requester_id, page, page_size)
        return [self._to_user_summary(row) for row in rows]

    def update_user_role(
        self,
        requester_id: str,
        user_id: str,
        role: str,
        ip: str | None = None,
    ) -> AdminUserSummary:
        """Update the role assigned to a user."""

        normalized_role = role.upper()
        self._repository.update_user_role(requester_id, user_id, normalized_role, ip)
        logger.info("User role updated", extra={"user_id": user_id, "role": role})
        return AdminUserSummary(user_id=user_id, role=normalized_role)

    def list_all_databases(
        self,
        requester_id: str,
        page: int = 1,
        page_size: int = 50,
        status_filter: str | None = None,
    ) -> list[DatabaseInstance]:
        """List every provisioned database across all users."""

        rows = self._repository.list_all_databases(
            requester_id,
            page,
            page_size,
            status_filter.upper() if status_filter else None,
        )
        return [self._to_database_instance(row) for row in rows]

    @staticmethod
    def _normalized(row: Mapping[str, Any]) -> dict[str, Any]:
        return {str(key).lower(): value for key, value in row.items()}

    def _to_user_summary(self, row: Mapping[str, Any]) -> AdminUserSummary:
        data = self._normalized(row)
        return AdminUserSummary(
            user_id=str(
                data.get("user_id") or data.get("id_usuario") or data.get("usuarioid") or data.get("id") or ""
            ),
            email=data.get("email") or data.get("correo"),
            name=data.get("name") or data.get("nombre"),
            role=data.get("role") or data.get("rol"),
            provider=data.get("provider") or data.get("proveedor"),
        )

    def _to_database_instance(self, row: Mapping[str, Any]) -> DatabaseInstance:
        return row_to_database_instance(row)
