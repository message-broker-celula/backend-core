"""Database integration exceptions.

These exceptions keep SQL Server and stored-procedure failures inside the
repository boundary and prevent raw driver errors from leaking into the API or
service layers.
"""

from __future__ import annotations


class DatabaseIntegrationError(RuntimeError):
    """Base exception for repository/database integration failures."""


class DatabaseConnectionError(DatabaseIntegrationError):
    """Raised when the SQL Server connection layer is unavailable."""


class StoredProcedureExecutionError(DatabaseIntegrationError):
    """Raised when a stored procedure invocation fails.

    The exception keeps the public contract opaque and exposes only a stable,
    domain-safe message instead of leaking database internals.
    """

    def __init__(self, procedure_name: str, detail: str = "Database operation failed") -> None:
        self.procedure_name = procedure_name
        self.detail = detail
        super().__init__(f"Stored procedure '{procedure_name}' failed: {detail}")


class RepositoryMappingError(DatabaseIntegrationError):
    """Raised when the repository cannot map a database result to a DTO."""


class ResourceNotFoundError(DatabaseIntegrationError):
    """Raised when a requested resource does not exist or is not owned by the caller."""
