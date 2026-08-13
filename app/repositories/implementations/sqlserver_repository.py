"""Concrete SQL Server-backed repository implementation.

This is the only repository implementation that knows SQL Server object names.
It calls stored procedures and functions with parameter placeholders only; all
business decisions remain in the database layer. Every domain-specific
repository (AuthRepository, DatabaseManagementRepository, AdminRepository,
CelulaRepository, AuditRepository) is a thin subclass of this one, wired with
the shared `StoredProcedureExecutor`.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from app.auth.schemas.auth_schemas import (
    OAuthRegistrationResult,
    OAuthUserIdentity,
    RefreshTokenResult,
)
from app.repositories.exceptions.database_exceptions import RepositoryMappingError
from app.repositories.interfaces.database_repository import DatabaseRepositoryProtocol
from app.repositories.interfaces.sp_executor import StoredProcedureExecutorProtocol


class SQLServerRepository(DatabaseRepositoryProtocol):
    """Repository implementation for SQL Server stored-procedure orchestration."""

    def __init__(self, executor: StoredProcedureExecutorProtocol) -> None:
        self._executor = executor

    # ------------------------------------------------------------------
    # Authentication
    # ------------------------------------------------------------------

    def register_oauth_user(
        self,
        provider: str,
        identity: OAuthUserIdentity,
        ip: str | None = None,
        user_agent: str | None = None,
    ) -> OAuthRegistrationResult:
        """Register or update an OAuth identity through sp_RegistrarOAuth."""

        sql = """
            DECLARE @id_usuario UNIQUEIDENTIFIER;
            DECLARE @es_nuevo BIT;

            EXEC sp_RegistrarOAuth
                @oauth_provider = ?,
                @oauth_id = ?,
                @nombre = ?,
                @correo = ?,
                @avatar = ?,
                @ip = ?,
                @user_agent = ?,
                @id_usuario = @id_usuario OUTPUT,
                @es_nuevo = @es_nuevo OUTPUT;

            SELECT @id_usuario AS id_usuario, @es_nuevo AS es_nuevo;
        """
        result = self._executor.execute_sql(
            sql,
            (
                provider.upper(),
                identity.provider_user_id,
                identity.name,
                identity.email,
                identity.avatar,
                ip,
                user_agent,
            ),
            procedure_name="sp_RegistrarOAuth",
        )
        row = self._first_row(result.rows, "sp_RegistrarOAuth")
        return OAuthRegistrationResult(
            user_id=self._read_string(row, "id_usuario", "UsuarioId", "user_id"),
            first_login=self._read_optional_bool(row, "es_nuevo", "EsNuevo"),
        )

    def issue_refresh_token(
        self,
        subject: str,
        ip: str | None = None,
        user_agent: str | None = None,
        validity_days: int = 30,
    ) -> str:
        """Issue the first refresh token for a session through sp_EmitirRefreshToken."""

        sql = """
            DECLARE @token_nuevo NVARCHAR(512);

            EXEC sp_EmitirRefreshToken
                @id_usuario = ?,
                @ip = ?,
                @user_agent = ?,
                @dias_validez = ?,
                @token_nuevo = @token_nuevo OUTPUT;

            SELECT @token_nuevo AS token_nuevo;
        """
        result = self._executor.execute_sql(
            sql,
            (subject, ip, user_agent, validity_days),
            procedure_name="sp_EmitirRefreshToken",
        )
        row = self._first_row(result.rows, "sp_EmitirRefreshToken")
        return self._read_string(row, "token_nuevo", "refresh_token", "token")

    def refresh_access_token(
        self,
        refresh_token: str,
        ip: str | None = None,
        user_agent: str | None = None,
        validity_days: int = 30,
    ) -> RefreshTokenResult:
        """Rotate and validate a refresh token through sp_RotarRefreshToken.

        If SQL Server detects the token was already rotated (reuse -- a sign
        of theft), the SP THROWs and revokes every session for that user;
        that surfaces here as a normal BusinessRuleViolationError like any
        other THROW, no special-casing needed in this method.
        """

        sql = """
            DECLARE @id_usuario UNIQUEIDENTIFIER;
            DECLARE @token_nuevo NVARCHAR(512);

            EXEC sp_RotarRefreshToken
                @token_actual = ?,
                @ip = ?,
                @user_agent = ?,
                @dias_validez = ?,
                @id_usuario = @id_usuario OUTPUT,
                @token_nuevo = @token_nuevo OUTPUT;

            SELECT @id_usuario AS id_usuario, @token_nuevo AS token_nuevo;
        """
        result = self._executor.execute_sql(
            sql,
            (refresh_token, ip, user_agent, validity_days),
            procedure_name="sp_RotarRefreshToken",
        )
        row = self._first_row(result.rows, "sp_RotarRefreshToken")
        return RefreshTokenResult(
            subject=self._read_string(row, "id_usuario", "UsuarioId", "subject", "sub"),
            refresh_token=self._read_string(row, "token_nuevo", "refresh_token", "RefreshToken", "token"),
            role=self._read_optional_string(row, "role", "Rol"),
            permissions=self._read_permissions(row, "permissions", "Permisos"),
        )

    def revoke_refresh_token(self, refresh_token: str, ip: str | None = None) -> None:
        self._executor.execute_sql(
            "EXEC sp_RevocarRefreshToken @token = ?, @ip = ?;",
            (refresh_token, ip),
            procedure_name="sp_RevocarRefreshToken",
        )

    def revoke_all_refresh_tokens(self, subject: str, ip: str | None = None) -> None:
        self._executor.execute_sql(
            "EXEC sp_RevocarTodosLosRefreshTokens @id_usuario = ?, @ip = ?;",
            (subject, ip),
            procedure_name="sp_RevocarTodosLosRefreshTokens",
        )

    # ------------------------------------------------------------------
    # Databases
    # ------------------------------------------------------------------

    def create_database(
        self,
        subject: str,
        payload: Mapping[str, Any],
        ip: str | None,
    ) -> str:
        """Create a database through sp_CrearBD and return @id_bd.

        host/puerto/usuario_bd/password_bd are supplied by the caller (e.g.
        the backend just provisioned a real MySQL/Postgres container) --
        SQL Server only stores and encrypts them, it does not invent them.
        """

        sql = """
            DECLARE @id_bd UNIQUEIDENTIFIER;

            EXEC sp_CrearBD
                @id_usuario = ?,
                @nombre_motor = ?,
                @version_motor = ?,
                @nombre_bd = ?,
                @host = ?,
                @puerto = ?,
                @usuario_bd = ?,
                @password_bd = ?,
                @ip = ?,
                @espacio_maximo_mb = ?,
                @conexiones_maximas = ?,
                @ttl_dias = ?,
                @id_celula = ?,
                @id_bd = @id_bd OUTPUT;

            SELECT @id_bd AS id_bd;
        """
        result = self._executor.execute_sql(
            sql,
            (
                subject,
                payload["nombre_motor"],
                payload["version_motor"],
                payload["nombre_bd"],
                payload["host"],
                payload["puerto"],
                payload["usuario_bd"],
                payload["password_bd"],
                ip,
                payload.get("espacio_maximo_mb", 20),
                payload.get("conexiones_maximas", 5),
                payload.get("ttl_dias", 30),
                payload.get("id_celula"),
            ),
            procedure_name="sp_CrearBD",
        )
        row = self._first_row(result.rows, "sp_CrearBD")
        return self._read_string(row, "id_bd", "BaseDatosId", "database_id")

    def get_database_credentials(self, subject: str, database_id: str | None = None) -> dict[str, str]:
        """Fetch decrypted connection credentials through sp_ObtenerCredenciales."""

        result = self._executor.execute_sql(
            "EXEC sp_ObtenerCredenciales @id_bd = ?, @id_usuario = ?;",
            (database_id, subject),
            procedure_name="sp_ObtenerCredenciales",
        )
        row = self._first_row(result.rows, "sp_ObtenerCredenciales")
        return {str(key): str(value) for key, value in row.items() if value is not None}

    def list_databases(self, subject: str) -> tuple[dict[str, Any], ...]:
        result = self._executor.execute_sql(
            "SELECT * FROM fn_BasesDeDatosPorUsuario(?);",
            (subject,),
            procedure_name="fn_BasesDeDatosPorUsuario",
        )
        return result.rows

    def get_database(self, subject: str, database_id: str) -> Mapping[str, Any]:
        result = self._executor.execute_sql(
            "SELECT * FROM fn_ObtenerBD(?, ?);",
            (database_id, subject),
            procedure_name="fn_ObtenerBD",
        )
        return self._first_row(result.rows, "fn_ObtenerBD")

    def delete_database(self, subject: str, database_id: str, ip: str | None = None) -> None:
        self._executor.execute_sql(
            "EXEC sp_EliminarBD @id_bd = ?, @id_usuario = ?, @ip = ?;",
            (database_id, subject, ip),
            procedure_name="sp_EliminarBD",
        )

    def get_database_usage(self, subject: str, database_id: str) -> Mapping[str, Any]:
        database = dict(self.get_database(subject, database_id))
        database["dias_restantes_ttl"] = self.get_ttl_days_remaining(database_id)
        database["porcentaje_espacio_usado"] = self.get_space_percentage(database_id)
        return database

    def pause_database(self, subject: str, database_id: str, ip: str | None = None) -> None:
        self._executor.execute_sql(
            "EXEC sp_PausarBD @id_bd = ?, @id_usuario = ?, @ip = ?;",
            (database_id, subject, ip),
            procedure_name="sp_PausarBD",
        )

    def resume_database(self, subject: str, database_id: str) -> None:
        """There is no sp_ReanudarBD in the current database contract."""

        raise RepositoryMappingError("sp_ReanudarBD is not part of the database contract")

    def register_activity(self, database_id: str, ttl_days: int = 30) -> None:
        self._executor.execute_sql(
            "EXEC sp_RegistrarActividad @id_bd = ?, @dias_ttl = ?;",
            (database_id, ttl_days),
            procedure_name="sp_RegistrarActividad",
        )

    def update_space(
        self,
        database_id: str,
        reported_space_mb: float,
        ip: str | None,
        ttl_days: int = 30,
    ) -> bool:
        sql = """
            DECLARE @permitir_escritura BIT;

            EXEC sp_ActualizarEspacio
                @id_bd = ?,
                @espacio_reportado_mb = ?,
                @ip = ?,
                @dias_ttl = ?,
                @permitir_escritura = @permitir_escritura OUTPUT;

            SELECT @permitir_escritura AS permitir_escritura;
        """
        result = self._executor.execute_sql(
            sql,
            (database_id, reported_space_mb, ip, ttl_days),
            procedure_name="sp_ActualizarEspacio",
        )
        row = self._first_row(result.rows, "sp_ActualizarEspacio")
        return bool(self._read_optional_bool(row, "permitir_escritura"))

    def validate_connection(self, database_id: str) -> bool:
        sql = """
            DECLARE @conexion_permitida BIT;

            EXEC sp_ValidarConexion
                @id_bd = ?,
                @conexion_permitida = @conexion_permitida OUTPUT;

            SELECT @conexion_permitida AS conexion_permitida;
        """
        result = self._executor.execute_sql(
            sql,
            (database_id,),
            procedure_name="sp_ValidarConexion",
        )
        row = self._first_row(result.rows, "sp_ValidarConexion")
        return bool(self._read_optional_bool(row, "conexion_permitida"))

    def release_connection(self, database_id: str) -> None:
        self._executor.execute_sql(
            "EXEC sp_LiberarConexion @id_bd = ?;",
            (database_id,),
            procedure_name="sp_LiberarConexion",
        )

    def get_ttl_days_remaining(self, database_id: str) -> int | None:
        result = self._executor.execute_sql(
            "SELECT fn_DiasRestantesTTL(?) AS dias_restantes;",
            (database_id,),
            procedure_name="fn_DiasRestantesTTL",
        )
        row = self._first_row(result.rows, "fn_DiasRestantesTTL")
        value = self._first_value(row)
        return int(value) if value is not None else None

    def get_space_percentage(self, database_id: str) -> float | None:
        result = self._executor.execute_sql(
            "SELECT fn_PorcentajeEspacioUsado(?) AS porcentaje_usado;",
            (database_id,),
            procedure_name="fn_PorcentajeEspacioUsado",
        )
        row = self._first_row(result.rows, "fn_PorcentajeEspacioUsado")
        value = self._first_value(row)
        return float(value) if value is not None else None

    def list_assigned_ports(self) -> tuple[int, ...]:
        """Host ports already assigned to active provisioned engines.

        Optimization only for PortAllocator's collision avoidance -- callers
        must tolerate this raising DatabaseIntegrationError (e.g. if
        fn_PuertosAsignados does not exist yet in SQL Server) and fall back to
        Docker's own port-bind failure as the authoritative collision check.
        """

        result = self._executor.execute_sql(
            "SELECT puerto FROM fn_PuertosAsignados();",
            (),
            procedure_name="fn_PuertosAsignados",
        )
        return tuple(
            int(row["puerto"])
            for row in result.rows
            if row.get("puerto") is not None
        )

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
        self._executor.execute_sql(
            """
            EXEC sp_RegistrarEvento
                @evento = ?,
                @id_usuario = ?,
                @id_bd = ?,
                @descripcion = ?,
                @ip = ?,
                @resultado = ?,
                @datos_adicionales = ?;
            """,
            (event, subject, database_id, description, ip, result, additional_data),
            procedure_name="sp_RegistrarEvento",
        )

    # ------------------------------------------------------------------
    # Administration and read-only metrics
    # ------------------------------------------------------------------

    def list_users(
        self,
        requester_id: str | None = None,
        page: int = 1,
        page_size: int = 50,
    ) -> tuple[dict[str, Any], ...]:
        result = self._executor.execute_sql(
            "EXEC sp_ListarUsuarios @id_usuario_solicitante = ?, @pagina = ?, @tamano_pagina = ?;",
            (requester_id, page, page_size),
            procedure_name="sp_ListarUsuarios",
        )
        return result.rows

    def update_user_role(
        self,
        requester_id: str,
        user_id: str,
        role: str,
        ip: str | None = None,
    ) -> None:
        self._executor.execute_sql(
            """
            EXEC sp_ActualizarRolUsuario
                @id_usuario_solicitante = ?,
                @id_usuario_objetivo = ?,
                @nuevo_rol = ?,
                @ip = ?;
            """,
            (requester_id, user_id, role, ip),
            procedure_name="sp_ActualizarRolUsuario",
        )

    def list_all_databases(
        self,
        requester_id: str | None = None,
        page: int = 1,
        page_size: int = 50,
        status_filter: str | None = None,
    ) -> tuple[dict[str, Any], ...]:
        result = self._executor.execute_sql(
            """
            EXEC sp_ListarTodasLasBasesDatos
                @id_usuario_solicitante = ?,
                @pagina = ?,
                @tamano_pagina = ?,
                @estado_filtro = ?;
            """,
            (requester_id, page, page_size, status_filter),
            procedure_name="sp_ListarTodasLasBasesDatos",
        )
        return result.rows

    # ------------------------------------------------------------------
    # Celulas and services
    # ------------------------------------------------------------------

    def create_celula(self, subject: str, name: str, ip: str | None = None) -> Mapping[str, Any]:
        sql = """
            DECLARE @id_celula UNIQUEIDENTIFIER;

            EXEC sp_CrearCelula
                @nombre_celula = ?,
                @id_usuario = ?,
                @ip = ?,
                @id_celula = @id_celula OUTPUT;

            SELECT @id_celula AS id_celula;
        """
        result = self._executor.execute_sql(
            sql,
            (name, subject, ip),
            procedure_name="sp_CrearCelula",
        )
        row = dict(self._first_row(result.rows, "sp_CrearCelula"))
        row.setdefault("nombre_celula", name)
        row.setdefault("id_usuario", subject)
        return row

    def list_celulas(self, subject: str) -> tuple[dict[str, Any], ...]:
        result = self._executor.execute_sql(
            "SELECT * FROM fn_MiCelula(?);",
            (subject,),
            procedure_name="fn_MiCelula",
        )
        return result.rows

    def get_celula(self, subject: str, celula_id: str) -> Mapping[str, Any]:
        result = self._executor.execute_sql(
            "SELECT * FROM fn_ObtenerCelula(?);",
            (celula_id,),
            procedure_name="fn_ObtenerCelula",
        )
        return self._first_row(result.rows, "fn_ObtenerCelula")

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
        sql = """
            DECLARE @id_servicio UNIQUEIDENTIFIER;

            EXEC sp_CrearServicio
                @id_celula = ?,
                @nombre_servicio = ?,
                @puerto_interno = ?,
                @id_bd = ?,
                @id_usuario = ?,
                @ip = ?,
                @id_servicio = @id_servicio OUTPUT;

            SELECT @id_servicio AS id_servicio;
        """
        result = self._executor.execute_sql(
            sql,
            (celula_id, service_name, port, database_id, subject, ip),
            procedure_name="sp_CrearServicio",
        )
        row = dict(self._first_row(result.rows, "sp_CrearServicio"))
        row.setdefault("id_celula", celula_id)
        row.setdefault("nombre_servicio", service_name)
        row.setdefault("tipo_servicio", service_type)
        row.setdefault("id_bd", database_id)
        return row

    def list_celula_services(self, subject: str, celula_id: str) -> tuple[dict[str, Any], ...]:
        result = self._executor.execute_sql(
            "SELECT * FROM fn_ServiciosPorCelula(?);",
            (celula_id,),
            procedure_name="fn_ServiciosPorCelula",
        )
        return result.rows

    def delete_celula_service(self, subject: str, celula_id: str, service_id: str) -> None:
        """There is no sp_EliminarServicioCelula -- pausing is the safe equivalent."""

        self.change_service_status(subject, service_id, "PAUSADO", None)

    def change_service_status(
        self,
        subject: str,
        service_id: str,
        new_status: str,
        ip: str | None,
    ) -> None:
        self._executor.execute_sql(
            "EXEC sp_CambiarEstadoServicio @id_servicio = ?, @nuevo_estado = ?, @id_usuario = ?, @ip = ?;",
            (service_id, new_status, subject, ip),
            procedure_name="sp_CambiarEstadoServicio",
        )

    # ------------------------------------------------------------------
    # Mapping helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _normalized(row: Mapping[str, Any]) -> dict[str, Any]:
        return {str(key).lower(): value for key, value in row.items()}

    def _first_row(self, rows: tuple[dict[str, Any], ...], procedure_name: str) -> Mapping[str, Any]:
        if not rows:
            raise RepositoryMappingError(f"{procedure_name} did not return a result row")
        return rows[0]

    def _first_value(self, row: Mapping[str, Any]) -> Any:
        return next(iter(row.values()), None)

    def _read_string(self, row: Mapping[str, Any], *keys: str) -> str:
        normalized = self._normalized(row)
        for key in keys:
            value = normalized.get(key.lower())
            if value is not None:
                return str(value)
        raise RepositoryMappingError("Stored procedure result is missing a required identifier")

    def _read_optional_bool(self, row: Mapping[str, Any], *keys: str) -> bool | None:
        normalized = self._normalized(row)
        for key in keys:
            value = normalized.get(key.lower())
            if value is None:
                continue
            if isinstance(value, bool):
                return value
            if isinstance(value, int):
                return bool(value)
            return str(value).strip().lower() in {"1", "true", "yes", "si", "sí"}
        return None

    def _read_optional_string(self, row: Mapping[str, Any], *keys: str) -> str | None:
        normalized = self._normalized(row)
        for key in keys:
            value = normalized.get(key.lower())
            if value is not None:
                return str(value)
        return None

    def _read_permissions(self, row: Mapping[str, Any], *keys: str) -> list[str]:
        value = self._read_optional_string(row, *keys)
        return [item.strip() for item in value.split(",") if item.strip()] if value else []
