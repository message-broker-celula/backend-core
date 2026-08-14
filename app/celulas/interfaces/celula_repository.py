"""Célula (team workspace) and service repository contract."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class CelulaRepositoryProtocol(Protocol):
    """Persistence contract for célula workspaces and their services."""

    def create_celula(self, subject: str, name: str, ip: str | None = None) -> Mapping[str, Any]:
        """Register a new célula workspace (sp_CrearCelula)."""
        ...

    def list_celulas(self, subject: str) -> tuple[dict[str, Any], ...]:
        """List célula workspaces visible to the subject (fn_MiCelula)."""
        ...

    def get_celula(self, subject: str, celula_id: str) -> Mapping[str, Any]:
        """Fetch a single célula workspace (fn_ObtenerCelula)."""
        ...

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
        """Register a subdomain-backed service under a célula (sp_CrearServicio)."""
        ...

    def list_celula_services(self, subject: str, celula_id: str) -> tuple[dict[str, Any], ...]:
        """List services registered under a célula (fn_ServiciosPorCelula)."""
        ...

    def delete_celula_service(
        self,
        subject: str,
        celula_id: str,
        service_id: str,
        ip: str | None = None,
    ) -> None:
        """Permanently remove a service registered under a célula (sp_EliminarServicio)."""
        ...

    def change_service_status(
        self,
        subject: str,
        service_id: str,
        new_status: str,
        ip: str | None,
    ) -> None:
        """Change a registered service status (sp_CambiarEstadoServicio)."""
        ...
