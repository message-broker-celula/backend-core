"""Audit event schema models."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class RegisterAuditEventRequest(BaseModel):
    """Request payload for sp_RegistrarEvento (generic events: LOGOUT, RENOVAR_TOKEN, ERROR...)."""

    model_config = ConfigDict(extra="forbid")

    evento: str = Field(..., examples=["LOGOUT", "RENOVAR_TOKEN", "ERROR"])
    id_bd: str | None = None
    descripcion: str
    resultado: str = Field(default="EXITO", pattern="^(EXITO|FALLO)$")
    datos_adicionales: str | None = None


class AuditEventResponse(BaseModel):
    """Acknowledgement returned after registering an audit event."""

    model_config = ConfigDict(extra="forbid")

    detail: str = "Event registered"
