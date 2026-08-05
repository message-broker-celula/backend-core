"""Célula repository protocol.

Thin Stored Procedure orchestration contract for célula (team workspace) and
subdomain-service provisioning.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Protocol


class CelulaRepositoryProtocol(Protocol):
    """Protocol for Stored Procedure-backed célula orchestration."""

    def create_celula(self, subject: str, name: str, ip: str | None = None) -> Mapping[str, Any]:
        """Create a new célula owned by the subject."""

    def list_celulas(self, subject: str) -> tuple[dict[str, Any], ...]:
        """List células visible to the subject."""

    def get_celula(self, subject: str, celula_id: str) -> Mapping[str, Any]:
        """Fetch a single célula scoped to the requesting subject."""

    def register_celula_service(
        self,
        subject: str,
        celula_id: str,
        service_name: str,
        service_type: str,
        database_id: str | None,
        port: int | None = None,
        ip: str | None = None,
    ) -> Mapping[str, Any]:
        """Register a subdomain-backed service under a célula."""

    def list_celula_services(self, subject: str, celula_id: str) -> tuple[dict[str, Any], ...]:
        """List services registered under a célula."""

    def delete_celula_service(self, subject: str, celula_id: str, service_id: str) -> None:
        """Remove a service registered under a célula."""

    def change_service_status(
        self,
        subject: str,
        service_id: str,
        new_status: str,
        ip: str | None,
    ) -> None:
        """Change a service status through sp_CambiarEstadoServicio."""
