"""Concrete SQL Server-backed repository implementation.

This repository is intentionally thin and delegates all business-facing
operations to the reusable stored procedure executor. It does not contain
business rules, inline SQL, or CRUD logic.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from app.auth.schemas.auth_schemas import (
    AccessTokenResponse,
    OAuthRegistrationResult,
    OAuthUserIdentity,
)
from app.repositories.exceptions.database_exceptions import (
    RepositoryMappingError,
    StoredProcedureExecutionError,
)
from app.repositories.interfaces.database_repository import DatabaseRepositoryProtocol
from app.repositories.interfaces.sp_executor import StoredProcedureExecutorProtocol

REGISTER_OAUTH_USER_SP = "sp_RegistrarOAuthUsuario"
PROVISION_DATABASE_SP = "sp_AprovisionarBaseDatos"
GET_DATABASE_CREDENTIALS_SP = "sp_ObtenerCredencialesDB"
REFRESH_ACCESS_TOKEN_SP = "sp_RotarRefreshToken"
REVOKE_REFRESH_TOKEN_SP = "sp_RevocarRefreshToken"
REVOKE_ALL_REFRESH_TOKENS_SP = "sp_RevocarRefreshTokensPorUsuario"

# --- Database lifecycle management (module: app.databases) ---
LIST_DATABASES_SP = "sp_ListarBasesDatosPorUsuario"
GET_DATABASE_SP = "sp_ObtenerBaseDatos"
DELETE_DATABASE_SP = "sp_EliminarBaseDatos"
GET_DATABASE_USAGE_SP = "sp_ObtenerUsoBaseDatos"
PAUSE_DATABASE_SP = "sp_PausarBaseDatos"
RESUME_DATABASE_SP = "sp_ReanudarBaseDatos"

# --- Administration (module: app.admin) ---
LIST_USERS_SP = "sp_ListarUsuarios"
UPDATE_USER_ROLE_SP = "sp_ActualizarRolUsuario"
LIST_ALL_DATABASES_SP = "sp_ListarTodasLasBasesDatos"

# --- Célula / service provisioning (module: app.celulas) ---
CREATE_CELULA_SP = "sp_CrearCelula"
LIST_CELULAS_SP = "sp_ListarCelulasPorUsuario"
GET_CELULA_SP = "sp_ObtenerCelula"
REGISTER_CELULA_SERVICE_SP = "sp_RegistrarServicioCelula"
LIST_CELULA_SERVICES_SP = "sp_ListarServiciosCelula"
DELETE_CELULA_SERVICE_SP = "sp_EliminarServicioCelula"


class SQLServerRepository(DatabaseRepositoryProtocol):
    """Repository implementation for SQL Server stored-procedure orchestration.

    The repository maps business-oriented service calls to stored-procedure
    execution through the reusable executor boundary.
    """

    def __init__(self, executor: StoredProcedureExecutorProtocol) -> None:
        """Initialize the repository with a stored procedure executor.

        Args:
            executor: Reusable SQL Server execution abstraction.
        """

        self._executor = executor

    def register_oauth_user(
        self,
        provider: str,
        identity: OAuthUserIdentity,
    ) -> OAuthRegistrationResult:
        """Register an OAuth-backed identity through the database layer.

        Args:
            provider: Provider name.
            identity: Provider-normalized OAuth identity.

        Returns:
            OAuthRegistrationResult: Typed registration contract.
        """

        result = self._executor.execute(
            REGISTER_OAUTH_USER_SP,
            {
                "Proveedor": provider,
                "UsuarioExternoId": identity.provider_user_id,
                "Email": identity.email,
                "Nombre": identity.name,
                "AvatarUrl": identity.avatar,
                "EmailVerificado": identity.verified_email,
            },
        )

        first_row = self._first_row(result.rows, REGISTER_OAUTH_USER_SP)
        user_id = self._read_string(first_row, "UserId", "UsuarioId", "user_id", "subject")
        first_login = self._read_optional_bool(
            first_row,
            "FirstLogin",
            "PrimerInicio",
            "first_login",
        )
        role = self._read_optional_string(
            first_row,
            "Role",
            "Rol",
            "role",
        )
        permissions = self._read_permissions(
            first_row,
            "Permissions",
            "Permisos",
            "permissions",
        )
        refresh_token = self._read_optional_string(
            first_row,
            "RefreshToken",
            "refresh_token",
            "new_refresh_token",
            "token",
        )
        return OAuthRegistrationResult(
            user_id=user_id,
            first_login=first_login,
            role=role,
            permissions=permissions,
            refresh_token=refresh_token,
        )

    def refresh_access_token(self, refresh_token: str) -> RefreshTokenResult:
        """Rotate and validate a refresh token through the database layer."""

        result = self._executor.execute(
            REFRESH_ACCESS_TOKEN_SP,
            {"RefreshToken": refresh_token},
        )
        first_row = self._first_row(result.rows, REFRESH_ACCESS_TOKEN_SP)
        subject = self._read_string(
            first_row,
            "UserId",
            "UsuarioId",
            "subject",
            "sub",
        )
        new_refresh_token = self._read_string(
            first_row,
            "RefreshToken",
            "refresh_token",
            "new_refresh_token",
            "token",
        )
        role = self._read_optional_string(
            first_row,
            "Role",
            "Rol",
            "role",
        )
        permissions = self._read_permissions(
            first_row,
            "Permissions",
            "Permisos",
            "permissions",
        )
        return RefreshTokenResult(
            subject=subject,
            refresh_token=new_refresh_token,
            role=role,
            permissions=permissions,
        )

    def revoke_refresh_token(self, refresh_token: str) -> None:
        """Revoke a refresh token in the database."""

        self._executor.execute(REVOKE_REFRESH_TOKEN_SP, {"RefreshToken": refresh_token})

    def revoke_all_refresh_tokens(self, subject: str) -> None:
        """Revoke all refresh tokens associated with a subject."""

        self._executor.execute(REVOKE_ALL_REFRESH_TOKENS_SP, {"UsuarioId": subject})

    def provision_database(self, subject: str) -> None:
        """Provision database resources through the SQL Server layer.

        Args:
            subject: Canonical subject identifier.
        """

        self._executor.execute(PROVISION_DATABASE_SP, {"UsuarioId": subject})

    def get_database_credentials(self, subject: str) -> dict[str, str]:
        """Fetch database credentials through the SQL Server layer.

        Args:
            subject: Canonical subject identifier.

        Returns:
            dict[str, str]: Database credential payload.
        """

        result = self._executor.execute(GET_DATABASE_CREDENTIALS_SP, {"UsuarioId": subject})
        first_row = self._first_row(result.rows, GET_DATABASE_CREDENTIALS_SP)
        credentials = {
            str(key): str(value)
            for key, value in first_row.items()
            if value is not None
        }
        if not credentials:
            raise RepositoryMappingError("Database credential procedure returned no values")
        return credentials

    # ------------------------------------------------------------------
    # Database lifecycle management
    # ------------------------------------------------------------------

    def list_databases(self, subject: str) -> tuple[dict[str, Any], ...]:
        """List the database instances owned by a subject.

        Args:
            subject: Canonical subject identifier.

        Returns:
            tuple[dict[str, Any], ...]: Raw rows describing each database.
        """

        result = self._executor.execute(LIST_DATABASES_SP, {"UsuarioId": subject})
        return result.rows

    def get_database(self, subject: str, database_id: str) -> Mapping[str, Any]:
        """Fetch a single database instance scoped to its owner.

        Args:
            subject: Canonical subject identifier.
            database_id: Database instance identifier.

        Returns:
            Mapping[str, Any]: Raw row describing the database.
        """

        result = self._executor.execute(
            GET_DATABASE_SP,
            {"UsuarioId": subject, "BaseDatosId": database_id},
        )
        return self._first_row(result.rows, GET_DATABASE_SP)

    def delete_database(self, subject: str, database_id: str) -> None:
        """Deprovision a database instance owned by the subject.

        Args:
            subject: Canonical subject identifier.
            database_id: Database instance identifier.
        """

        self._executor.execute(
            DELETE_DATABASE_SP,
            {"UsuarioId": subject, "BaseDatosId": database_id},
        )

    def get_database_usage(self, subject: str, database_id: str) -> Mapping[str, Any]:
        """Fetch storage/connection usage for a database instance.

        Args:
            subject: Canonical subject identifier.
            database_id: Database instance identifier.

        Returns:
            Mapping[str, Any]: Raw usage row.
        """

        result = self._executor.execute(
            GET_DATABASE_USAGE_SP,
            {"UsuarioId": subject, "BaseDatosId": database_id},
        )
        return self._first_row(result.rows, GET_DATABASE_USAGE_SP)

    def pause_database(self, subject: str, database_id: str) -> None:
        """Pause a database instance (e.g. inactivity TTL policy).

        Args:
            subject: Canonical subject identifier.
            database_id: Database instance identifier.
        """

        self._executor.execute(
            PAUSE_DATABASE_SP,
            {"UsuarioId": subject, "BaseDatosId": database_id},
        )

    def resume_database(self, subject: str, database_id: str) -> None:
        """Resume a previously paused database instance.

        Args:
            subject: Canonical subject identifier.
            database_id: Database instance identifier.
        """

        self._executor.execute(
            RESUME_DATABASE_SP,
            {"UsuarioId": subject, "BaseDatosId": database_id},
        )

    # ------------------------------------------------------------------
    # Administration
    # ------------------------------------------------------------------

    def list_users(self) -> tuple[dict[str, Any], ...]:
        """List all registered users for administrative oversight.

        Returns:
            tuple[dict[str, Any], ...]: Raw rows describing each user.
        """

        result = self._executor.execute(LIST_USERS_SP, {})
        return result.rows

    def update_user_role(self, user_id: str, role: str) -> None:
        """Update the role assigned to a user.

        Args:
            user_id: Canonical subject identifier of the target user.
            role: New role to assign.
        """

        self._executor.execute(
            UPDATE_USER_ROLE_SP,
            {"UsuarioId": user_id, "Rol": role},
        )

    def list_all_databases(self) -> tuple[dict[str, Any], ...]:
        """List every provisioned database across all users (admin view).

        Returns:
            tuple[dict[str, Any], ...]: Raw rows describing each database.
        """

        result = self._executor.execute(LIST_ALL_DATABASES_SP, {})
        return result.rows

    # ------------------------------------------------------------------
    # Célula / service provisioning
    # ------------------------------------------------------------------

    def create_celula(self, subject: str, name: str) -> Mapping[str, Any]:
        """Create a new célula (team workspace) owned by the subject.

        Args:
            subject: Canonical subject identifier of the owner.
            name: Célula name, used to derive its subdomain slug.

        Returns:
            Mapping[str, Any]: Raw row describing the created célula.
        """

        result = self._executor.execute(
            CREATE_CELULA_SP,
            {"UsuarioId": subject, "Nombre": name},
        )
        return self._first_row(result.rows, CREATE_CELULA_SP)

    def list_celulas(self, subject: str) -> tuple[dict[str, Any], ...]:
        """List células visible to the subject.

        Args:
            subject: Canonical subject identifier.

        Returns:
            tuple[dict[str, Any], ...]: Raw rows describing each célula.
        """

        result = self._executor.execute(LIST_CELULAS_SP, {"UsuarioId": subject})
        return result.rows

    def get_celula(self, subject: str, celula_id: str) -> Mapping[str, Any]:
        """Fetch a single célula scoped to the requesting subject.

        Args:
            subject: Canonical subject identifier.
            celula_id: Célula identifier.

        Returns:
            Mapping[str, Any]: Raw row describing the célula.
        """

        result = self._executor.execute(
            GET_CELULA_SP,
            {"UsuarioId": subject, "CelulaId": celula_id},
        )
        return self._first_row(result.rows, GET_CELULA_SP)

    def register_celula_service(
        self,
        subject: str,
        celula_id: str,
        service_name: str,
        service_type: str,
        database_id: str | None,
    ) -> Mapping[str, Any]:
        """Register a subdomain-backed service under a célula.

        Args:
            subject: Canonical subject identifier of the requester.
            celula_id: Célula identifier.
            service_name: Service slug (e.g. "api", "auth", "payments").
            service_type: Service classification (e.g. "frontend", "api").
            database_id: Optional database instance backing the service.

        Returns:
            Mapping[str, Any]: Raw row describing the registered service.
        """

        result = self._executor.execute(
            REGISTER_CELULA_SERVICE_SP,
            {
                "UsuarioId": subject,
                "CelulaId": celula_id,
                "NombreServicio": service_name,
                "TipoServicio": service_type,
                "BaseDatosId": database_id,
            },
        )
        return self._first_row(result.rows, REGISTER_CELULA_SERVICE_SP)

    def list_celula_services(self, subject: str, celula_id: str) -> tuple[dict[str, Any], ...]:
        """List services registered under a célula.

        Args:
            subject: Canonical subject identifier.
            celula_id: Célula identifier.

        Returns:
            tuple[dict[str, Any], ...]: Raw rows describing each service.
        """

        result = self._executor.execute(
            LIST_CELULA_SERVICES_SP,
            {"UsuarioId": subject, "CelulaId": celula_id},
        )
        return result.rows

    def delete_celula_service(self, subject: str, celula_id: str, service_id: str) -> None:
        """Remove a service registered under a célula.

        Args:
            subject: Canonical subject identifier.
            celula_id: Célula identifier.
            service_id: Service identifier to remove.
        """

        self._executor.execute(
            DELETE_CELULA_SERVICE_SP,
            {"UsuarioId": subject, "CelulaId": celula_id, "ServicioId": service_id},
        )

    def _first_row(
        self,
        rows: tuple[dict[str, Any], ...],
        procedure_name: str,
    ) -> Mapping[str, Any]:
        """Return the first result row or raise a sanitized mapping error."""

        if not rows:
            raise RepositoryMappingError(f"{procedure_name} did not return a result row")
        return rows[0]

    def _read_string(self, row: Mapping[str, Any], *keys: str) -> str:
        """Read a required string field from a stored procedure row."""

        normalized = {key.lower(): value for key, value in row.items()}
        for key in keys:
            value = normalized.get(key.lower())
            if isinstance(value, str) and value:
                return value
            if value is not None:
                return str(value)
        raise RepositoryMappingError("Stored procedure result is missing the user identifier")

    def _read_optional_bool(self, row: Mapping[str, Any], *keys: str) -> bool | None:
        """Read an optional boolean field from a stored procedure row."""

        normalized = {key.lower(): value for key, value in row.items()}
        for key in keys:
            value = normalized.get(key.lower())
            if value is None:
                continue
            if isinstance(value, bool):
                return value
            if isinstance(value, int):
                return bool(value)
            if isinstance(value, str):
                return value.strip().lower() in {"1", "true", "yes", "si", "sí"}
        return None

    def _read_optional_string(self, row: Mapping[str, Any], *keys: str) -> str | None:
        """Read an optional string field from a stored procedure row."""

        normalized = {key.lower(): value for key, value in row.items()}
        for key in keys:
            value = normalized.get(key.lower())
            if value is None:
                continue
            if isinstance(value, str):
                return value
            return str(value)
        return None

    def _read_permissions(self, row: Mapping[str, Any], *keys: str) -> list[str]:
        """Read an optional permissions collection from a stored procedure row."""

        normalized = {key.lower(): value for key, value in row.items()}
        for key in keys:
            value = normalized.get(key.lower())
            if value is None:
                continue
            if isinstance(value, str):
                return [item.strip() for item in value.split(",") if item.strip()]
            if isinstance(value, (list, tuple)):
                return [str(item) for item in value if item is not None]
            return [str(value)]
        return []
