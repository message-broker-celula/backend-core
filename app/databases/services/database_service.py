"""Database lifecycle service orchestration.

This module stays intentionally thin: it shapes Stored Procedure result rows
into typed DTOs for the API layer and never implements business rules
(storage limits, TTL policy, connection quotas) — those live exclusively in
the database layer, per the project's database-centric architecture.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any

from app.databases.interfaces.database_repository import (
    DatabaseManagementRepositoryProtocol,
)
from app.databases.schemas.database_schemas import (
    DatabaseActionResponse,
    DatabaseCredentials,
    DatabaseInstance,
    DatabaseStatus,
    DatabaseUsage,
)
from app.repositories.exceptions.database_exceptions import (
    RepositoryMappingError,
    ResourceNotFoundError,
)

logger = logging.getLogger(__name__)


class DatabaseService:
    """Coordinate database lifecycle orchestration for the `/databases` API."""

    def __init__(self, repository: DatabaseManagementRepositoryProtocol) -> None:
        """Initialize the service with a database management repository.

        Args:
            repository: Repository adapter used to reach the Stored Procedure
                layer. All business decisions (quotas, TTL, permissions) are
                resolved by the database itself.
        """

        self._repository = repository

    def provision_database(self, subject: str) -> None:
        """Provision an additional database instance for the subject."""

        self._repository.provision_database(subject)
        logger.info("Database provisioned", extra={"subject": subject})

    def list_databases(self, subject: str) -> list[DatabaseInstance]:
        """List the database instances owned by the subject."""

        rows = self._repository.list_databases(subject)
        return [self._to_instance(row) for row in rows]

    def get_database(self, subject: str, database_id: str) -> DatabaseInstance:
        """Fetch a single database instance scoped to its owner.

        Raises:
            ResourceNotFoundError: When the database does not exist or is not
                owned by the requesting subject.
        """

        try:
            row = self._repository.get_database(subject, database_id)
        except RepositoryMappingError as exc:
            raise ResourceNotFoundError(f"Database '{database_id}' was not found") from exc
        return self._to_instance(row)

    def delete_database(self, subject: str, database_id: str) -> DatabaseActionResponse:
        """Deprovision a database instance owned by the subject."""

        self._repository.delete_database(subject, database_id)
        logger.info(
            "Database deleted",
            extra={"subject": subject, "database_id": database_id},
        )
        return DatabaseActionResponse(
            database_id=database_id,
            status=DatabaseStatus.DELETED,
            detail="Database deprovisioned",
        )

    def get_credentials(self, subject: str, database_id: str | None = None) -> DatabaseCredentials:
        """Fetch connection credentials for the subject's database.

        Args:
            subject: Canonical subject identifier.
            database_id: Reserved for future multi-database credential
                lookups; the current Stored Procedure resolves credentials by
                subject alone.
        """

        raw_credentials = self._repository.get_database_credentials(subject)
        return self._to_credentials(raw_credentials)

    def get_usage(self, subject: str, database_id: str) -> DatabaseUsage:
        """Fetch storage/connection usage for a database instance."""

        try:
            row = self._repository.get_database_usage(subject, database_id)
        except RepositoryMappingError as exc:
            raise ResourceNotFoundError(
                f"Usage information for database '{database_id}' was not found"
            ) from exc
        return self._to_usage(database_id, row)

    def pause_database(self, subject: str, database_id: str) -> DatabaseActionResponse:
        """Pause a database instance."""

        self._repository.pause_database(subject, database_id)
        logger.info(
            "Database paused",
            extra={"subject": subject, "database_id": database_id},
        )
        return DatabaseActionResponse(
            database_id=database_id,
            status=DatabaseStatus.PAUSED,
            detail="Database paused",
        )

    def resume_database(self, subject: str, database_id: str) -> DatabaseActionResponse:
        """Resume a previously paused database instance."""

        self._repository.resume_database(subject, database_id)
        logger.info(
            "Database resumed",
            extra={"subject": subject, "database_id": database_id},
        )
        return DatabaseActionResponse(
            database_id=database_id,
            status=DatabaseStatus.ACTIVE,
            detail="Database resumed",
        )

    # ------------------------------------------------------------------
    # Row -> DTO mapping helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _normalized(row: Mapping[str, Any]) -> dict[str, Any]:
        return {str(key).lower(): value for key, value in row.items()}

    def _to_instance(self, row: Mapping[str, Any]) -> DatabaseInstance:
        data = self._normalized(row)
        status_value = str(
            data.get("status") or data.get("estado") or DatabaseStatus.UNKNOWN.value
        ).lower()
        try:
            status = DatabaseStatus(status_value)
        except ValueError:
            status = DatabaseStatus.UNKNOWN

        return DatabaseInstance(
            database_id=str(
                data.get("database_id")
                or data.get("basedatosid")
                or data.get("id")
                or ""
            ),
            name=data.get("name") or data.get("nombre"),
            status=status,
            created_at=data.get("created_at") or data.get("fechacreacion"),
            ttl_expires_at=data.get("ttl_expires_at") or data.get("fechaexpiracion"),
            storage_limit_mb=data.get("storage_limit_mb") or data.get("limitealmacenamientomb"),
            storage_used_mb=data.get("storage_used_mb") or data.get("almacenamientousadomb"),
        )

    def _to_credentials(self, raw: Mapping[str, str]) -> DatabaseCredentials:
        data = self._normalized(raw)
        port_raw = data.get("port") or data.get("puerto")
        port = int(port_raw) if port_raw is not None and str(port_raw).isdigit() else None

        return DatabaseCredentials(
            host=data.get("host") or data.get("servidor"),
            port=port,
            database_name=data.get("database_name")
            or data.get("basedatos")
            or data.get("database"),
            username=data.get("username") or data.get("usuario"),
            password=data.get("password") or data.get("contrasena") or data.get("contraseña"),
            connection_string=data.get("connection_string") or data.get("cadenaconexion"),
            **{k: v for k, v in raw.items() if k.lower() not in {
                "host", "servidor", "port", "puerto", "database_name", "basedatos",
                "database", "username", "usuario", "password", "contrasena",
                "contraseña", "connection_string", "cadenaconexion",
            }},
        )

    def _to_usage(self, database_id: str, row: Mapping[str, Any]) -> DatabaseUsage:
        data = self._normalized(row)
        limit_mb = data.get("storage_limit_mb") or data.get("limitealmacenamientomb")
        used_mb = data.get("storage_used_mb") or data.get("almacenamientousadomb")
        percentage = None
        if limit_mb and used_mb:
            try:
                percentage = round((float(used_mb) / float(limit_mb)) * 100, 2)
            except (TypeError, ValueError, ZeroDivisionError):
                percentage = None

        return DatabaseUsage(
            database_id=database_id,
            storage_limit_mb=limit_mb,
            storage_used_mb=used_mb,
            storage_percentage=percentage,
            active_connections=data.get("active_connections") or data.get("conexionesactivas"),
            max_connections=data.get("max_connections") or data.get("maxconexiones"),
        )
