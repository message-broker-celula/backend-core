"""External-client repository adapter."""

from __future__ import annotations

from app.repositories.implementations.sqlserver_repository import SQLServerRepository
from app.repositories.sqlserver.executor import StoredProcedureExecutor


class ExternalClientRepository(SQLServerRepository):
    """Default Stored Procedure-backed external-client repository."""

    def __init__(self) -> None:
        super().__init__(executor=StoredProcedureExecutor())
