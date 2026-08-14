"""Database lifecycle service orchestration.

This module stays intentionally thin: it shapes Stored Procedure result rows
into typed DTOs for the API layer and never implements business rules
(storage limits, TTL policy, connection quotas) -- those live exclusively in
the database layer, per the project's database-centric architecture.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any

from app.databases.interfaces.database_repository import (
    DatabaseManagementRepositoryProtocol,
)
from app.databases.row_mapping import normalize_row, pick_first, row_to_database_instance
from app.databases.schemas.database_schemas import (
    DatabaseActionResponse,
    DatabaseCredentials,
    DatabaseInstance,
    DatabaseStatus,
    DatabaseUsage,
    UpdateDatabaseSpaceResponse,
    ValidateConnectionResponse,
)
from app.provisioning.exceptions.provisioning_exceptions import ProvisioningError
from app.provisioning.services.provisioning_service import DatabaseProvisioningService
from app.repositories.exceptions.database_exceptions import (
    RepositoryMappingError,
    ResourceNotFoundError,
)

logger = logging.getLogger(__name__)


class DatabaseService:
    """Coordinate database lifecycle orchestration for the `/databases` API."""

    def __init__(
        self,
        repository: DatabaseManagementRepositoryProtocol,
        provisioning: DatabaseProvisioningService,
    ) -> None:
        """Initialize the service with a database management repository.

        Args:
            repository: Repository adapter used to reach the Stored Procedure
                layer. All business decisions (quotas, TTL, permissions) are
                resolved by the database itself.
            provisioning: Orchestrates the real engine container behind each
                database instance (see app.provisioning).
        """

        self._repository = repository
        self._provisioning = provisioning

    def create_database(
        self,
        subject: str,
        payload: Mapping[str, Any],
        ip: str | None,
    ) -> DatabaseActionResponse:
        """Create an additional database instance for the subject.

        Provisions a real engine container first -- sp_CrearBD requires real
        host/puerto/usuario_bd/password_bd as *input*, it does not invent
        them. If sp_CrearBD then rejects the create (quota, duplicate name,
        etc.), the just-created container is torn down instead of leaking.
        """

        provisioned = self._provisioning.provision(
            engine=str(payload["nombre_motor"]).strip().upper(),
            version=str(payload["version_motor"]),
            requested_name=str(payload["nombre_bd"]),
        )
        enriched = dict(payload)
        enriched.update(
            host=provisioned.host,
            puerto=provisioned.port,
            usuario_bd=provisioned.username,
            password_bd=provisioned.password,
            nombre_bd=provisioned.database_name,
        )
        try:
            database_id = self._repository.create_database(subject, enriched, ip)
        except Exception:
            logger.error(
                "sp_CrearBD failed after provisioning; removing orphaned container",
                extra={"subject": subject, "container_name": provisioned.container_name},
            )
            try:
                self._provisioning.deprovision(port=provisioned.port)
            except ProvisioningError as cleanup_exc:
                logger.error("Failed to clean up orphaned container", exc_info=cleanup_exc)
            raise

        logger.info("Database created", extra={"subject": subject, "database_id": database_id})
        return DatabaseActionResponse(
            database_id=database_id,
            status=DatabaseStatus.ACTIVE,
            detail="Database created",
        )

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

    def delete_database(
        self,
        subject: str,
        database_id: str,
        ip: str | None,
    ) -> DatabaseActionResponse:
        """Deprovision a database instance owned by the subject.

        Removes the real container first -- if that fails, the SQL row is
        left untouched and the call is safe to retry, instead of deleting
        the record for a container that's still actually running.
        """

        port = self._extract_port(self._repository.get_database(subject, database_id))
        self._provisioning.deprovision(port=port)
        self._repository.delete_database(subject, database_id, ip)
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

        sp_ObtenerCredenciales only returns usuario_bd/password_bd/algoritmo
        (the encrypted columns) -- host/puerto/nombre_bd live on the
        BasesDeDatos row itself, already available via get_database. Merged
        here so callers get one complete DatabaseCredentials instead of
        having to combine two endpoints themselves.
        """

        raw_credentials = dict(self._repository.get_database_credentials(subject, database_id or ""))
        if database_id:
            try:
                data = normalize_row(self._repository.get_database(subject, database_id))
                raw_credentials.setdefault("host", pick_first(data, "host"))
                raw_credentials.setdefault("puerto", pick_first(data, "puerto"))
                raw_credentials.setdefault("nombre_bd", pick_first(data, "nombre_bd"))
            except RepositoryMappingError:
                pass
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

    def pause_database(
        self,
        subject: str,
        database_id: str,
        ip: str | None,
    ) -> DatabaseActionResponse:
        """Pause a database instance.

        Stops (not removes) the real container first, then flips the SQL
        Server status flag.
        """

        port = self._extract_port(self._repository.get_database(subject, database_id))
        self._provisioning.stop(port=port)
        self._repository.pause_database(subject, database_id, ip)
        logger.info(
            "Database paused",
            extra={"subject": subject, "database_id": database_id},
        )
        return DatabaseActionResponse(
            database_id=database_id,
            status=DatabaseStatus.PAUSED,
            detail="Database paused",
        )

    def resume_database(
        self,
        subject: str,
        database_id: str,
        ip: str | None = None,
    ) -> DatabaseActionResponse:
        """Resume a previously paused database instance.

        Restarts the real container first, then flips the SQL Server status
        flag back to ACTIVA via sp_ReanudarBD.
        """

        port = self._extract_port(self._repository.get_database(subject, database_id))
        self._provisioning.start(port=port)
        self._repository.resume_database(subject, database_id, ip)
        logger.info(
            "Database resumed",
            extra={"subject": subject, "database_id": database_id},
        )
        return DatabaseActionResponse(
            database_id=database_id,
            status=DatabaseStatus.ACTIVE,
            detail="Database resumed",
        )

    def register_activity(self, database_id: str, ttl_days: int = 30) -> DatabaseActionResponse:
        """Refresh database TTL activity."""

        self._repository.register_activity(database_id, ttl_days)
        return DatabaseActionResponse(
            database_id=database_id,
            status=DatabaseStatus.ACTIVE,
            detail="Database activity registered",
        )

    def update_space(
        self,
        database_id: str,
        reported_space_mb: float,
        ip: str | None,
        ttl_days: int = 30,
    ) -> UpdateDatabaseSpaceResponse:
        """Report storage usage and return the database write decision."""

        allowed = self._repository.update_space(database_id, reported_space_mb, ip, ttl_days)
        return UpdateDatabaseSpaceResponse(permitir_escritura=allowed)

    def validate_connection(self, database_id: str) -> ValidateConnectionResponse:
        """Ask SQL Server whether another user DB connection can be opened."""

        allowed = self._repository.validate_connection(database_id)
        return ValidateConnectionResponse(conexion_permitida=allowed)

    def release_connection(self, database_id: str) -> DatabaseActionResponse:
        """Release one active user DB connection counter."""

        self._repository.release_connection(database_id)
        return DatabaseActionResponse(
            database_id=database_id,
            status=DatabaseStatus.ACTIVE,
            detail="Database connection released",
        )

    def get_ttl_days_remaining(self, database_id: str) -> int | None:
        """Read fn_DiasRestantesTTL."""

        return self._repository.get_ttl_days_remaining(database_id)

    def get_space_percentage(self, database_id: str) -> float | None:
        """Read fn_PorcentajeEspacioUsado."""

        return self._repository.get_space_percentage(database_id)

    # ------------------------------------------------------------------
    # Row -> DTO mapping helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _normalized(row: Mapping[str, Any]) -> dict[str, Any]:
        return normalize_row(row)

    @staticmethod
    def _extract_port(row: Mapping[str, Any]) -> int:
        data = normalize_row(row)
        port = pick_first(data, "puerto", "port")
        if port is None:
            raise ProvisioningError("Database row is missing its provisioned host port")
        return int(port)

    def _to_instance(self, row: Mapping[str, Any]) -> DatabaseInstance:
        return row_to_database_instance(row)

    def _to_credentials(self, raw: Mapping[str, str]) -> DatabaseCredentials:
        data = self._normalized(raw)
        port_raw = data.get("port") or data.get("puerto")
        port = int(port_raw) if port_raw is not None and str(port_raw).isdigit() else None

        return DatabaseCredentials(
            host=data.get("host") or data.get("servidor"),
            port=port,
            database_name=data.get("database_name")
            or data.get("nombre_bd")
            or data.get("basedatos")
            or data.get("database"),
            username=data.get("username") or data.get("usuario_bd") or data.get("usuario"),
            password=(
                data.get("password")
                or data.get("password_bd")
                or data.get("contrasena")
                or data.get("contraseña")
            ),
            algoritmo=data.get("algoritmo") or data.get("algorithm"),
            connection_string=data.get("connection_string") or data.get("cadenaconexion"),
            **{k: v for k, v in raw.items() if k.lower() not in {
                "host", "servidor", "port", "puerto", "database_name", "nombre_bd", "basedatos",
                "database", "username", "usuario_bd", "usuario", "password", "password_bd",
                "contrasena", "contraseña", "algoritmo", "algorithm", "connection_string", "cadenaconexion",
            }},
        )

    def _to_usage(self, database_id: str, row: Mapping[str, Any]) -> DatabaseUsage:
        data = self._normalized(row)
        limit_mb = pick_first(data, "storage_limit_mb", "espacio_maximo_mb", "limitealmacenamientomb")
        used_mb = pick_first(data, "storage_used_mb", "espacio_actual_mb", "almacenamientousadomb")
        percentage = None
        if limit_mb and used_mb is not None:
            try:
                percentage = round((float(used_mb) / float(limit_mb)) * 100, 2)
            except (TypeError, ValueError, ZeroDivisionError):
                percentage = None

        storage_percentage = pick_first(data, "porcentaje_espacio_usado")
        if storage_percentage is None:
            storage_percentage = percentage

        return DatabaseUsage(
            database_id=database_id,
            storage_limit_mb=limit_mb,
            storage_used_mb=used_mb,
            storage_percentage=storage_percentage,
            active_connections=pick_first(
                data, "active_connections", "conexiones_actuales", "conexionesactivas"
            ),
            max_connections=pick_first(data, "max_connections", "conexiones_maximas", "maxconexiones"),
        )
