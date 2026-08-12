"""Administration schema models."""

from __future__ import annotations

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
