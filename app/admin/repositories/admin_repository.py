"""Administration repository adapter.

Exposes the module-specific repository name used by the dependency layer
while delegating all Stored Procedure execution to the shared SQL Server
repository implementation.
"""

from __future__ import annotations

from app.repositories.implementations.sqlserver_repository import SQLServerRepository
from app.repositories.sqlserver.executor import StoredProcedureExecutor


class AdminRepository(SQLServerRepository):
    """Default Stored Procedure-backed administration repository."""

    def __init__(self) -> None:
        """Initialize the repository with the shared stored procedure executor."""

        super().__init__(executor=StoredProcedureExecutor())
