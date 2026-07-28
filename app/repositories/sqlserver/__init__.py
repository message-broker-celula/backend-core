"""SQL Server repository implementation package.

This package is the only concrete database integration boundary for the backend.
It keeps all provider-specific database logic under one reusable module.
"""

from app.repositories.sqlserver.executor import StoredProcedureExecutor

__all__ = ["StoredProcedureExecutor"]
