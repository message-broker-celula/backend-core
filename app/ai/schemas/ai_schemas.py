"""AI Gateway key schema models.

Mirrors the Ollama Gateway's own response shapes where practical (see its
"Guía de consumo") -- this backend is a thin orchestration layer over an
already-built, already-documented external API.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class RegisterAiKeyRequest(BaseModel):
    """Optional overrides for gateway client registration.

    name/email are always taken from the authenticated user's own platform
    profile (Usuarios.nombre/correo), never from client input -- a caller
    can't register a gateway key under someone else's identity.
    """

    model_config = ConfigDict(extra="forbid")

    organization: str | None = Field(default=None, max_length=150)
    intended_use: str | None = Field(default=None, max_length=500)


class AiKeyIssuedResponse(BaseModel):
    """Response for issuing or rotating a key -- the raw api_key is shown ONCE.

    Mirrors the gateway's own "shown only once" model: this backend does not
    re-expose a previously-issued key after this response, only its
    key_prefix, matching the gateway's own security posture.
    """

    model_config = ConfigDict(extra="forbid")

    client_id: int
    api_key: str
    key_prefix: str
    base_url: str = Field(description="Use this as the OpenAI SDK's base_url (already includes /v1).")


class AiKeyLimits(BaseModel):
    """Rate/quota limits reported by the gateway for this key."""

    model_config = ConfigDict(extra="allow")

    requests_per_minute: int | None = None
    daily_token_limit: int | None = None
    monthly_token_limit: int | None = None
    expires_at: datetime | None = None


class AiKeyStatusResponse(BaseModel):
    """Status for the caller's own AI Gateway key -- never includes the raw key."""

    model_config = ConfigDict(extra="allow")

    client_id: int
    key_prefix: str
    status: str
    can_call_api: bool
    limits: AiKeyLimits | None = None
    last_used_at: datetime | None = None


class AiUsageBucket(BaseModel):
    """One row of the usage breakdown (by day/model/endpoint)."""

    model_config = ConfigDict(extra="allow")

    key: str
    requests: int
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int


class AiUsageResponse(BaseModel):
    """Consumption for the caller's own AI Gateway key, proxied from the gateway."""

    model_config = ConfigDict(extra="allow")

    start: str
    end: str
    total_requests: int
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    by_day: list[AiUsageBucket] = Field(default_factory=list)
    by_model: list[AiUsageBucket] = Field(default_factory=list)
    by_endpoint: list[AiUsageBucket] = Field(default_factory=list)


class AiKeyActionResponse(BaseModel):
    """Generic acknowledgement returned after revoking a key."""

    model_config = ConfigDict(extra="forbid")

    detail: str
