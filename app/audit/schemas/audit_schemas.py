"""HTTP DTOs for generic audit events."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class RegisterAuditEventRequest(BaseModel):
    """Payload for sp_RegistrarEvento."""

    model_config = ConfigDict(extra="forbid")

    evento: str = Field(..., min_length=1, max_length=64)
    id_bd: str | None = None
    descripcion: str = Field(..., min_length=1, max_length=1000)
    resultado: Literal["EXITO", "FALLO"] = "EXITO"
    datos_adicionales: dict[str, Any] | str | None = None


class AuditEventResponse(BaseModel):
    """Acknowledgement returned after registering an audit event."""

    model_config = ConfigDict(extra="forbid")

    detail: str = "Event registered"
