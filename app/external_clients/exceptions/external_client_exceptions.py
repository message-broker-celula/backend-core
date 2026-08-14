"""External-client (machine-to-machine) domain exceptions.

Subclasses DatabaseIntegrationError so the existing `except
DatabaseIntegrationError` -> 503 route handling covers transport/SQL
failures, same principle as app.provisioning, app.dns, and app.ai.
InvalidApiKeyError is the one exception the API-key auth dependency maps
to 401 itself, since an invalid credential is never a service outage.
"""

from __future__ import annotations

from app.repositories.exceptions.database_exceptions import DatabaseIntegrationError


class ExternalClientError(DatabaseIntegrationError):
    """Base exception for external-client registration/auth failures."""


class InvalidApiKeyError(ExternalClientError):
    """Raised when a presented API key is missing, unknown, or revoked."""
