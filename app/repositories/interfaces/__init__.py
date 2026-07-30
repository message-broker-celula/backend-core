"""Repository interface package for shared data access abstractions."""

from app.repositories.interfaces.database_repository import DatabaseRepositoryProtocol
from app.repositories.interfaces.sp_executor import (
    StoredProcedureExecutionResult,
    StoredProcedureExecutorProtocol,
)

__all__ = [
    "DatabaseRepositoryProtocol",
    "StoredProcedureExecutionResult",
    "StoredProcedureExecutorProtocol",
]
