"""Repository exception package for safe database error handling."""

from app.repositories.exceptions.database_exceptions import (
    DatabaseConnectionError,
    DatabaseIntegrationError,
    RepositoryMappingError,
    StoredProcedureExecutionError,
)

__all__ = [
    "DatabaseConnectionError",
    "DatabaseIntegrationError",
    "RepositoryMappingError",
    "StoredProcedureExecutionError",
]
