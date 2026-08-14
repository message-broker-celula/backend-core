"""Contract for talking to the Ollama Gateway over HTTP.

Declares WHAT this backend needs from the gateway -- register a client,
check its status, rotate its key, read its usage -- without knowing HOW
the transport works.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable


@dataclass(frozen=True, slots=True)
class GatewayCredential:
    """Result of registering or rotating a key with the gateway."""

    client_id: int
    api_key: str
    key_prefix: str


@runtime_checkable
class AiGatewayClientProtocol(Protocol):
    """Persistence-free contract for the Ollama Gateway's client API."""

    def register(
        self, *, name: str, email: str, organization: str | None, intended_use: str | None
    ) -> GatewayCredential:
        """Register a new gateway client, returning its immediately-usable key.

        Raises:
            AiGatewayError: For any gateway/transport failure other than a
                duplicate email (which the caller is expected to have
                already ruled out via its own ClavesIA state).
        """
        ...

    def get_status(self, api_key: str) -> dict[str, Any]:
        """Return the gateway's own /public/clients/me payload for this key."""
        ...

    def rotate(self, api_key: str) -> GatewayCredential:
        """Rotate the given key, returning the new one. The old key stops working immediately."""
        ...

    def get_usage(self, api_key: str, start: str | None = None, end: str | None = None) -> dict[str, Any]:
        """Return the gateway's own /public/clients/me/usage payload for this key."""
        ...
