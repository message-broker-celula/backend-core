"""AI Gateway key repository adapter."""

from __future__ import annotations

from app.repositories.implementations.sqlserver_repository import SQLServerRepository
from app.repositories.sqlserver.executor import StoredProcedureExecutor


class AiKeyRepository(SQLServerRepository):
    """Default Stored Procedure-backed AI Gateway key repository."""

    def __init__(self) -> None:
        super().__init__(executor=StoredProcedureExecutor())
