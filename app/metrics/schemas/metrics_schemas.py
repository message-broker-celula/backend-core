"""Public platform metrics schema models."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class PublicMetrics(BaseModel):
    """Response for GET /metrics (fn_MetricasPublicas).

    Field names are camelCase aliases to match the landing page's existing
    `PublicMetrics` TypeScript contract exactly (`totalUsers`,
    `totalDatabases`, ...) -- the route serializes with `by_alias=True`.
    """

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    total_users: int = Field(alias="totalUsers")
    total_databases: int = Field(alias="totalDatabases")
    active_databases: int = Field(alias="activeDatabases")
    total_logins: int = Field(alias="totalLogins")
    active_users: int = Field(alias="activeUsers")
    # Percentage points (e.g. 99.9), not a 0-1 fraction -- the frontend
    # renders it directly as `${value.toFixed(digits)}%`.
    availability: float
