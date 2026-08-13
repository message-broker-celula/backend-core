"""Database lifecycle schema models.

These DTOs represent the typed HTTP boundary for provisioning, inspecting,
and retiring the SQL Server databases assigned to each user.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class DatabaseStatus(str, Enum):
    """Lifecycle state of a provisioned database instance."""

    ACTIVE = "active"
    PAUSED = "paused"
    DELETED = "deleted"
    UNKNOWN = "unknown"


class CreateDatabaseRequest(BaseModel):
    """Request payload for sp_CrearBD.

    host/puerto/usuario_bd/password_bd are NOT accepted from the client --
    no caller can know them in advance. The backend provisions a real engine
    container via the provisioning sidecar and generates these values itself
    (see app.provisioning) before calling sp_CrearBD; SQL Server only stores
    and encrypts them, it does not invent them.
    """

    model_config = ConfigDict(extra="forbid")

    nombre_motor: str = Field(..., examples=["MYSQL"])
    version_motor: str = Field(..., examples=["8.4"])
    nombre_bd: str
    espacio_maximo_mb: int = 20
    conexiones_maximas: int = 5
    ttl_dias: int = 30
    id_celula: str | None = None


class UpdateDatabaseSpaceRequest(BaseModel):
    """Request payload for sp_ActualizarEspacio."""

    model_config = ConfigDict(extra="forbid")

    espacio_reportado_mb: float
    dias_ttl: int = 30


class UpdateDatabaseSpaceResponse(BaseModel):
    """Response returned after sp_ActualizarEspacio."""

    model_config = ConfigDict(extra="forbid")

    permitir_escritura: bool


class ValidateConnectionResponse(BaseModel):
    """Response returned after sp_ValidarConexion."""

    model_config = ConfigDict(extra="forbid")

    conexion_permitida: bool


class DaysRemainingResponse(BaseModel):
    """TTL days remaining for a database (fn_DiasRestantesTTL)."""

    model_config = ConfigDict(extra="forbid")

    database_id: str
    dias_restantes: int | None = None


class SpacePercentageResponse(BaseModel):
    """Storage usage percentage for a database (fn_PorcentajeEspacioUsado)."""

    model_config = ConfigDict(extra="forbid")

    database_id: str
    porcentaje_usado: float | None = None


class DatabaseInstance(BaseModel):
    """Summary of a provisioned database instance."""

    model_config = ConfigDict(extra="forbid")

    database_id: str
    name: str | None = None
    status: DatabaseStatus = DatabaseStatus.UNKNOWN
    created_at: datetime | None = None
    ttl_expires_at: datetime | None = None
    storage_limit_mb: float | None = None
    storage_used_mb: float | None = None


class DatabaseListResponse(BaseModel):
    """Collection of database instances owned by the requesting user."""

    model_config = ConfigDict(extra="forbid")

    databases: list[DatabaseInstance] = Field(default_factory=list)


class DatabaseCredentials(BaseModel):
    """Connection credentials for a provisioned database instance."""

    model_config = ConfigDict(extra="allow")

    host: str | None = None
    port: int | None = None
    database_name: str | None = None
    username: str | None = None
    password: str | None = None
    algoritmo: str | None = None
    connection_string: str | None = None


class DatabaseUsage(BaseModel):
    """Storage and connection usage for a provisioned database instance."""

    model_config = ConfigDict(extra="forbid")

    database_id: str
    storage_limit_mb: float | None = None
    storage_used_mb: float | None = None
    storage_percentage: float | None = None
    active_connections: int | None = None
    max_connections: int | None = None


class DatabaseActionResponse(BaseModel):
    """Generic acknowledgement returned after a lifecycle action."""

    model_config = ConfigDict(extra="forbid")

    database_id: str
    status: DatabaseStatus
    detail: str
