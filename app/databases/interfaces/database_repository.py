"""Database management repository protocol.

This interface defines the Stored Procedure orchestration contract used by
the `/databases` HTTP boundary. Implementations must stay thin adapters over
SQL Server Stored Procedures; no business validation belongs here.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Protocol


class DatabaseManagementRepositoryProtocol(Protocol):
    """Protocol for Stored Procedure-backed database lifecycle management."""

    def create_database(
        self,
        subject: str,
        payload: Mapping[str, Any],
        ip: str | None,
    ) -> str:
        """Create a database instance through sp_CrearBD."""

    def get_database_credentials(self, subject: str, database_id: str) -> dict[str, str]:
        """Fetch connection credentials for a subject's database."""

    def list_databases(self, subject: str) -> tuple[dict[str, Any], ...]:
        """List the database instances owned by a subject."""

    def get_database(self, subject: str, database_id: str) -> Mapping[str, Any]:
        """Fetch a single database instance scoped to its owner."""

    def delete_database(self, subject: str, database_id: str, ip: str | None) -> None:
        """Deprovision a database instance owned by the subject."""

    def get_database_usage(self, subject: str, database_id: str) -> Mapping[str, Any]:
        """Fetch storage/connection usage for a database instance."""

    def pause_database(self, subject: str, database_id: str, ip: str | None) -> None:
        """Pause a database instance."""

    def register_activity(self, database_id: str, ttl_days: int = 30) -> None:
        """Refresh TTL activity for a database."""

    def update_space(
        self,
        database_id: str,
        reported_space_mb: float,
        ip: str | None,
        ttl_days: int = 30,
    ) -> bool:
        """Report database space and return whether writes are allowed."""

    def validate_connection(self, database_id: str) -> bool:
        """Validate whether a new user database connection can be opened."""

    def release_connection(self, database_id: str) -> None:
        """Release an active user database connection."""

    def get_ttl_days_remaining(self, database_id: str) -> int | None:
        """Read fn_DiasRestantesTTL."""

    def get_space_percentage(self, database_id: str) -> float | None:
        """Read fn_PorcentajeEspacioUsado."""

    def register_event(
        self,
        event: str,
        subject: str | None,
        database_id: str | None,
        description: str,
        ip: str | None,
        result: str,
        additional_data: str | None = None,
    ) -> None:
        """Register a generic audit event through sp_RegistrarEvento."""
