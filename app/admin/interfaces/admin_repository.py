"""Administration repository protocol.

Thin Stored Procedure orchestration contract for administrative oversight of
users and provisioned databases.
"""

from __future__ import annotations

from typing import Any, Protocol


class AdminRepositoryProtocol(Protocol):
    """Protocol for Stored Procedure-backed administrative operations."""

    def list_users(
        self,
        requester_id: str,
        page: int = 1,
        page_size: int = 50,
    ) -> tuple[dict[str, Any], ...]:
        """List all registered users."""

    def update_user_role(
        self,
        requester_id: str,
        user_id: str,
        role: str,
        ip: str | None = None,
    ) -> None:
        """Update the role assigned to a user."""

    def list_all_databases(
        self,
        requester_id: str,
        page: int = 1,
        page_size: int = 50,
        status_filter: str | None = None,
    ) -> tuple[dict[str, Any], ...]:
        """List every provisioned database across all users."""
