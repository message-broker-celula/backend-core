"""Administration schema models.

DTOs for administrative oversight endpoints: user/role management and a
global view over provisioned databases across all users.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from app.databases.schemas.database_schemas import DatabaseInstance


class AdminUserSummary(BaseModel):
    """Summary of a registered user for administrative listings."""

    model_config = ConfigDict(extra="forbid")

    user_id: str
    email: str | None = None
    name: str | None = None
    role: str | None = None
    provider: str | None = None


class AdminUserListResponse(BaseModel):
    """Collection of users for administrative oversight."""

    model_config = ConfigDict(extra="forbid")

    users: list[AdminUserSummary] = Field(default_factory=list)


class UpdateUserRoleRequest(BaseModel):
    """Request payload to change a user's role."""

    model_config = ConfigDict(extra="forbid")

    role: str = Field(..., pattern="^(ESTUDIANTE|ADMIN|estudiante|admin)$")


class AdminDatabaseListResponse(BaseModel):
    """Global view of every provisioned database, across all users."""

    model_config = ConfigDict(extra="forbid")

    databases: list[DatabaseInstance] = Field(default_factory=list)
