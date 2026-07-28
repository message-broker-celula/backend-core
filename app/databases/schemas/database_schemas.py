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
    """Request payload to provision an additional database instance."""

    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(
        default=None,
        description="Optional friendly name for the database instance.",
    )


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
