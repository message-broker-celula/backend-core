"""Authentication repository adapter.

This module exposes the auth-specific repository name used by the dependency
layer while delegating all stored procedure execution to the shared SQL Server
repository implementation.
"""

from app.repositories.implementations.sqlserver_repository import SQLServerRepository
from app.repositories.sqlserver.executor import StoredProcedureExecutor


class AuthRepository(SQLServerRepository):
    """Default Stored Procedure-backed authentication repository."""

    def __init__(self) -> None:
        """Initialize the repository with the shared stored procedure executor."""

        super().__init__(executor=StoredProcedureExecutor())
