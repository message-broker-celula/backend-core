"""External-client (machine-to-machine) schema models.

These DTOs represent the typed HTTP boundary for `/public/postgres` --
other teams' own backends registering for and consuming Postgres
provisioning without a human OAuth login, mirroring the Ollama Gateway's
own `/public/clients/register` contract.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

# Loose "looks like an email" check -- real deliverability isn't this
# backend's concern, this only rejects obviously malformed input before it
# ever reaches sp_RegistrarClienteExterno.
_EMAIL_PATTERN = r"^[^@\s]+@[^@\s]+\.[^@\s]+$"


class RegisterExternalClientRequest(BaseModel):
    """Request payload for sp_RegistrarClienteExterno."""

    model_config = ConfigDict(extra="forbid")

    team_name: str = Field(..., min_length=1, max_length=150, examples=["Idempotencia"])
    contact_email: str = Field(..., pattern=_EMAIL_PATTERN, max_length=255, examples=["equipo@idempotencia.dev"])


class ExternalClientKeyResponse(BaseModel):
    """Response for registering or rotating -- the raw api_key is shown ONCE.

    Mirrors AiKeyIssuedResponse's "shown only once" model: this backend does
    not re-expose a previously-issued key after this response.
    """

    model_config = ConfigDict(extra="forbid")

    client_id: str
    api_key: str
    key_prefix: str


class CreateExternalDatabaseRequest(BaseModel):
    """Request payload for `POST /public/postgres/databases`.

    Deliberately has no `nombre_motor`/`version_motor` fields -- this
    channel is specifically the Postgres service this team offers to other
    teams, the engine is fixed server-side, never taken from the client.
    """

    model_config = ConfigDict(extra="forbid")

    nombre_bd: str = ""


class ExternalClientMetricsResponse(BaseModel):
    """Aggregate view of the caller's own PostgreSQL usage.

    Scoped strictly to the calling client's own databases (there is no
    cross-client visibility here) -- generic by construction, so any team
    that registers under /public/postgres/register gets the same metrics,
    not just the first one that asked for it.
    """

    model_config = ConfigDict(extra="forbid")

    total_databases: int
    active_databases: int
    storage_used_mb: float
    storage_limit_mb: float


class ExternalClientActionResponse(BaseModel):
    """Generic acknowledgement returned after revoking a key."""

    model_config = ConfigDict(extra="forbid")

    detail: str
