"""Célula (team workspace) and service schema models."""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class CelulaServiceType(str, Enum):
    """Kind of subdomain-backed service registered under a célula."""

    FRONTEND = "frontend"
    API = "api"
    AUTH = "auth"
    PAYMENTS = "payments"
    OTHER = "other"


class CreateCelulaRequest(BaseModel):
    """Request payload for sp_CrearCelula."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(..., min_length=1, max_length=63, examples=["alpha"])


class RegisterCelulaServiceRequest(BaseModel):
    """Request payload for sp_CrearServicio."""

    model_config = ConfigDict(extra="forbid")

    service_name: str = Field(..., min_length=1, max_length=63, examples=["api"])
    service_type: CelulaServiceType = CelulaServiceType.OTHER
    database_id: str | None = None
    puerto_interno: int | None = None


class ChangeServiceStatusRequest(BaseModel):
    """Request payload for sp_CambiarEstadoServicio."""

    model_config = ConfigDict(extra="forbid")

    nuevo_estado: str = Field(..., pattern="^(ACTIVO|CAIDO|PAUSADO)$")


class Celula(BaseModel):
    """A célula (team) workspace, addressed at [celula].<root_domain>."""

    model_config = ConfigDict(extra="forbid")

    celula_id: str
    name: str
    domain: str | None = None
    owner_subject: str | None = None


class CelulaListResponse(BaseModel):
    """Collection of célula workspaces."""

    model_config = ConfigDict(extra="forbid")

    celulas: list[Celula] = Field(default_factory=list)


class CelulaService(BaseModel):
    """A service registered under a célula, addressed at [servicio].[celula].<root_domain>."""

    model_config = ConfigDict(extra="forbid")

    service_id: str
    celula_id: str
    service_name: str
    service_type: CelulaServiceType
    domain: str | None = None
    database_id: str | None = None


class CelulaServiceListResponse(BaseModel):
    """Collection of services registered under a célula."""

    model_config = ConfigDict(extra="forbid")

    services: list[CelulaService] = Field(default_factory=list)
