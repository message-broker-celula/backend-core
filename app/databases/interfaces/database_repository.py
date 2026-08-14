"""Database-lifecycle repository contract.

Declares WHAT the database-provisioning domain can do -- create, inspect,
pause, delete, report usage -- without knowing HOW. No SQL Server, no
Stored Procedure names appear here.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class DatabaseManagementRepositoryProtocol(Protocol):
    """Persistence contract for provisioned database instances."""

    def create_database(self, subject: str, payload: Mapping[str, Any], ip: str | None) -> str:
        """Provision a new database instance, returning its id (sp_CrearBD)."""
        ...

    def get_database_credentials(self, subject: str, database_id: str | None = None) -> dict[str, str]:
        """Return decrypted connection credentials (sp_ObtenerCredenciales)."""
        ...

    def list_databases(self, subject: str) -> tuple[dict[str, Any], ...]:
        """List every database instance owned by the subject (fn_BasesDeDatosPorUsuario)."""
        ...

    def get_database(self, subject: str, database_id: str) -> Mapping[str, Any]:
        """Fetch a single database instance scoped to its owner (fn_ObtenerBD)."""
        ...

    def delete_database(self, subject: str, database_id: str, ip: str | None = None) -> None:
        """Deprovision a database instance (sp_EliminarBD)."""
        ...

    def get_database_usage(self, subject: str, database_id: str) -> Mapping[str, Any]:
        """Fetch storage/connection usage for a database instance."""
        ...

    def pause_database(self, subject: str, database_id: str, ip: str | None = None) -> None:
        """Pause a database instance (sp_PausarBD)."""
        ...

    def resume_database(self, subject: str, database_id: str, ip: str | None = None) -> None:
        """Resume a previously paused database instance (sp_ReanudarBD)."""
        ...

    def register_activity(self, database_id: str, ttl_days: int = 30) -> None:
        """Refresh the database TTL activity marker (sp_RegistrarActividad)."""
        ...

    def update_space(
        self,
        database_id: str,
        reported_space_mb: float,
        ip: str | None,
        ttl_days: int = 30,
    ) -> bool:
        """Report storage usage; returns whether further writes are allowed (sp_ActualizarEspacio)."""
        ...

    def validate_connection(self, database_id: str) -> bool:
        """Ask whether another connection may be opened (sp_ValidarConexion)."""
        ...

    def release_connection(self, database_id: str) -> None:
        """Release a connection slot (sp_LiberarConexion)."""
        ...

    def get_ttl_days_remaining(self, database_id: str) -> int | None:
        """Return remaining TTL days (fn_DiasRestantesTTL)."""
        ...

    def get_space_percentage(self, database_id: str) -> float | None:
        """Return storage usage percentage (fn_PorcentajeEspacioUsado)."""
        ...

    def list_assigned_ports(self) -> tuple[int, ...]:
        """Return host ports already assigned to active provisioned engines (fn_PuertosAsignados)."""
        ...

    def list_engines(self) -> tuple[Mapping[str, Any], ...]:
        """Return the active engine/version catalog (fn_MotoresDisponibles)."""
        ...
