"""Administration repository contract.

`sp_ListarUsuarios`, `sp_ActualizarRolUsuario`, and
`sp_ListarTodasLasBasesDatos` all validate the ADMIN role themselves inside
the database -- this Protocol only describes the shape, the actual
authorization is enforced twice: here at the HTTP boundary via
`require_role("admin")`, and again inside the Stored Procedure itself.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class AdminRepositoryProtocol(Protocol):
    """Persistence contract for administrative oversight operations."""

    def list_users(
        self,
        requester_id: str | None = None,
        page: int = 1,
        page_size: int = 50,
    ) -> tuple[dict[str, Any], ...]:
        """List every registered user (sp_ListarUsuarios)."""
        ...

    def update_user_role(
        self,
        requester_id: str,
        user_id: str,
        role: str,
        ip: str | None = None,
    ) -> None:
        """Update the role assigned to a user (sp_ActualizarRolUsuario)."""
        ...

    def list_all_databases(
        self,
        requester_id: str | None = None,
        page: int = 1,
        page_size: int = 50,
        status_filter: str | None = None,
    ) -> tuple[dict[str, Any], ...]:
        """List every provisioned database across all users (sp_ListarTodasLasBasesDatos)."""
        ...
