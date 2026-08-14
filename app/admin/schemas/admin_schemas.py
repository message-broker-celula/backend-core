"""Administration schema models."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.databases.schemas.database_schemas import DatabaseInstance


class AdminUserSummary(BaseModel):
    """Summary row for the admin user listing (sp_ListarUsuarios)."""

    model_config = ConfigDict(extra="forbid")

    user_id: str
    email: str | None = None
    name: str | None = None
    role: str | None = None
    provider: str | None = None


class AdminUserListResponse(BaseModel):
    """Paginated collection of registered users."""

    model_config = ConfigDict(extra="forbid")

    users: list[AdminUserSummary] = Field(default_factory=list)


class UpdateUserRoleRequest(BaseModel):
    """Request payload for sp_ActualizarRolUsuario."""

    model_config = ConfigDict(extra="forbid")

    role: str = Field(..., pattern="^(ESTUDIANTE|ADMIN)$")


class AdminDatabaseListResponse(BaseModel):
    """Global, paginated view of every provisioned database."""

    model_config = ConfigDict(extra="forbid")

    databases: list[DatabaseInstance] = Field(default_factory=list)


class AdminServiceSummary(BaseModel):
    """Summary row for the admin service listing (sp_ListarTodosLosServicios)."""

    model_config = ConfigDict(extra="forbid")

    service_id: str
    celula_id: str
    celula_name: str | None = None
    service_name: str | None = None
    domain: str | None = None
    status: str | None = None
    database_id: str | None = None
    created_at: datetime | None = None


class AdminServiceListResponse(BaseModel):
    """Global, paginated view of every célula service (DNS subdomain)."""

    model_config = ConfigDict(extra="forbid")

    services: list[AdminServiceSummary] = Field(default_factory=list)
