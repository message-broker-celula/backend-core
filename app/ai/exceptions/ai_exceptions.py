"""AI Gateway domain exceptions.

Subclasses DatabaseIntegrationError so the existing `except
DatabaseIntegrationError` -> 503 route handling covers every gateway
failure, same principle as app.provisioning and app.dns.
"""

from __future__ import annotations

from app.repositories.exceptions.database_exceptions import DatabaseIntegrationError


class AiGatewayError(DatabaseIntegrationError):
    """Base exception for Ollama Gateway request failures."""


class AiGatewayAuthError(AiGatewayError):
    """Raised when the gateway rejects a stored API key (revoked/invalid upstream)."""
