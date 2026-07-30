"""Célula (team workspace) schema models.

DTOs for creating célula workspaces and registering the subdomain-backed
services under them, per the `[servicio].[celula].andrescortes.dev` scheme.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class CelulaServiceType(str, Enum):
    """Classification of a service registered under a célula."""

    FRONTEND = "frontend"
    API = "api"
    AUTH = "auth"
    PAYMENTS = "payments"
    OTHER = "other"


class CreateCelulaRequest(BaseModel):
    """Request payload to create a new célula workspace."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(
        ...,
        min_length=2,
        max_length=63,
        description="Slug used to derive the célula's subdomain, e.g. 'alpha'.",
    )


class Celula(BaseModel):
    """A célula (team) workspace."""

    model_config = ConfigDict(extra="forbid")

    celula_id: str
    name: str
    domain: str | None = None
    owner_subject: str | None = None


class CelulaListResponse(BaseModel):
    """Collection of célula workspaces visible to the requester."""

    model_config = ConfigDict(extra="forbid")

    celulas: list[Celula] = Field(default_factory=list)


class RegisterCelulaServiceRequest(BaseModel):
    """Request payload to register a subdomain-backed service under a célula."""

    model_config = ConfigDict(extra="forbid")

    service_name: str = Field(
        ...,
        min_length=1,
        max_length=63,
        description="Service slug, e.g. 'api', 'auth', 'payments'.",
    )
    service_type: CelulaServiceType = CelulaServiceType.API
    database_id: str | None = Field(
        default=None,
        description="Optional database instance backing this service.",
    )


class CelulaService(BaseModel):
    """A subdomain-backed service registered under a célula."""

    model_config = ConfigDict(extra="forbid")

    service_id: str
    celula_id: str
    service_name: str
    service_type: CelulaServiceType = CelulaServiceType.OTHER
    domain: str | None = None
    database_id: str | None = None


class CelulaServiceListResponse(BaseModel):
    """Collection of services registered under a célula."""

    model_config = ConfigDict(extra="forbid")

    services: list[CelulaService] = Field(default_factory=list)
