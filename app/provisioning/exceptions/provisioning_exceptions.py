"""Provisioning-domain exceptions.

All subclass DatabaseIntegrationError so the existing `except
DatabaseIntegrationError` -> 503 handling in database_routes.py already
covers every provisioning failure with zero route changes.
"""

from __future__ import annotations

from app.repositories.exceptions.database_exceptions import DatabaseIntegrationError


class ProvisioningError(DatabaseIntegrationError):
    """Base exception for database engine provisioning failures."""


class ProvisionerRequestError(ProvisioningError):
    """Raised when the sidecar is unreachable or returns an unexpected error."""


class ProvisioningTimeoutError(ProvisioningError):
    """Raised when a provisioned container never became ready in time."""


class PortInUseError(ProvisioningError):
    """Raised when the sidecar/Docker reports the requested host port is taken.

    Caught internally by DatabaseProvisioningService's allocation retry loop;
    should not normally escape to the API layer.
    """


class PortAllocationExhaustedError(ProvisioningError):
    """Raised when no free port could be found after the configured retry budget."""
