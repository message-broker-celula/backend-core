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

    def provision_database(self, subject: str) -> None:
        """Provision a new database instance for a subject."""

    def get_database_credentials(self, subject: str) -> dict[str, str]:
        """Fetch connection credentials for a subject's database."""

    def list_databases(self, subject: str) -> tuple[dict[str, Any], ...]:
        """List the database instances owned by a subject."""

    def get_database(self, subject: str, database_id: str) -> Mapping[str, Any]:
        """Fetch a single database instance scoped to its owner."""

    def delete_database(self, subject: str, database_id: str) -> None:
        """Deprovision a database instance owned by the subject."""

    def get_database_usage(self, subject: str, database_id: str) -> Mapping[str, Any]:
        """Fetch storage/connection usage for a database instance."""

    def pause_database(self, subject: str, database_id: str) -> None:
        """Pause a database instance."""

    def resume_database(self, subject: str, database_id: str) -> None:
        """Resume a previously paused database instance."""
