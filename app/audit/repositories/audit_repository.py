"""Stored Procedure-backed audit repository adapter."""

from __future__ import annotations

from app.repositories.implementations.sqlserver_repository import SQLServerRepository
from app.repositories.sqlserver.executor import StoredProcedureExecutor


class AuditRepository(SQLServerRepository):
    """Default audit repository using the shared SQL Server implementation."""

    def __init__(self) -> None:
        super().__init__(executor=StoredProcedureExecutor())
