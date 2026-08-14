"""External-client (machine-to-machine) repository contract.

Declares WHAT the external-client domain can do -- register a team,
validate/rotate/revoke an API key -- without knowing HOW. No SQL Server,
no Stored Procedure names appear here.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class ExternalClientRepositoryProtocol(Protocol):
    """Persistence contract for external API-key clients (ClavesApiExternas)."""

    def register_external_client(
        self,
        team_name: str,
        contact_email: str,
        ip: str | None = None,
    ) -> Mapping[str, Any]:
        """Register a new external client, returning its raw API key once (sp_RegistrarClienteExterno)."""
        ...

    def validate_api_key(self, api_key: str) -> str | None:
        """Return the shadow subject (id_usuario) for a valid, active key, or None (sp_ValidarClaveApiExterna)."""
        ...

    def rotate_api_key(self, api_key: str, ip: str | None = None) -> Mapping[str, Any]:
        """Invalidate the current key and issue a new one (sp_RotarClaveApiExterna)."""
        ...

    def revoke_api_key(self, api_key: str, ip: str | None = None) -> None:
        """Revoke the current key (sp_RevocarClaveApiExterna)."""
        ...
