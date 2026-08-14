"""DNS provisioning domain exceptions.

All subclass DatabaseIntegrationError so the existing `except
DatabaseIntegrationError` -> 503 handling already in celula_routes.py
covers every DNS failure with zero route changes (same principle as
app.provisioning.exceptions).
"""

from __future__ import annotations

from app.repositories.exceptions.database_exceptions import DatabaseIntegrationError


class DnsProviderError(DatabaseIntegrationError):
    """Base exception for Cloudflare DNS provisioning failures."""


class DnsRecordConflictError(DnsProviderError):
    """Raised when a DNS record for the requested name already exists.

    Invalid name *format* is a client input error, not a provider failure --
    that case reuses BusinessRuleViolationError directly (imported from
    app.repositories.exceptions.database_exceptions), the same way
    app.provisioning handles an unsupported engine, so it maps to 400 via
    the existing `except BusinessRuleViolationError` handling instead of
    503 like every DnsProviderError here.
    """
