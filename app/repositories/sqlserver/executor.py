"""Reusable SQL Server stored procedure executor.

This module is the only concrete database gateway in the backend. It keeps
connection management, parameter binding, and error sanitization in one place
so future modules can reuse the same execution contract without duplicating
connection logic.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from typing import Any

from pydantic import SecretStr

from app.core.config import settings
from app.repositories.exceptions.database_exceptions import (
    BusinessRuleViolationError,
    DatabaseConnectionError,
    StoredProcedureExecutionError,
)
from app.repositories.interfaces.sp_executor import (
    StoredProcedureExecutionResult,
    StoredProcedureExecutorProtocol,
)

logger = logging.getLogger(__name__)


class StoredProcedureExecutor(StoredProcedureExecutorProtocol):
    """Concrete SQL Server stored procedure executor.

    This executor is intentionally thin and reusable. Its role is to encapsulate
    connection setup, stored procedure invocation, and result mapping in a way
    that services and repositories never need to know about SQL Server internals.
    """

    def __init__(
        self,
        connection_string: SecretStr | None = None,
        timeout: int = 30,
    ) -> None:
        """Initialize the executor.

        Args:
            connection_string: Optional SQL Server connection string.
            timeout: Default query timeout for stored procedure execution.
        """

        database_settings = settings.database
        self._connection_string = connection_string or database_settings.connection_string
        self._timeout = timeout or database_settings.stored_procedure_timeout_seconds

    def execute_sql(
        self,
        sql: str,
        parameters: Sequence[Any] = (),
        *,
        procedure_name: str,
        timeout: int | None = None,
    ) -> StoredProcedureExecutionResult:
        """Execute a raw SQL statement through the SQL Server execution boundary.
    
        Args:
            sql: Full SQL text (DECLARE/EXEC/SELECT block), owned by the caller.
            parameters: Ordered values bound to the "?" placeholders in `sql`.
            procedure_name: Stored Procedure name, used for logging/error context.
            timeout: Optional timeout override in seconds.
    
        Returns:
            StoredProcedureExecutionResult: Typed execution result.
    
        Raises:
            DatabaseConnectionError: When SQL Server is unreachable or the driver
                is unavailable.
            BusinessRuleViolationError: When the Stored Procedure rejects the
                operation via THROW (the message is safe to show the end user).
            StoredProcedureExecutionError: For any other execution failure.
        """
    
        logger.info(
            "Executing stored procedure",
            extra={"procedure_name": procedure_name, "parameter_count": len(parameters)},
        )
    
        connection_string = self._connection_string.get_secret_value()
        if not connection_string:
            raise DatabaseConnectionError("SQL Server connection string is not configured")
    
        try:
            import pyodbc
        except ImportError as exc:
            raise DatabaseConnectionError("SQL Server driver dependency is not installed") from exc
    
        try:
            connection = pyodbc.connect(connection_string, timeout=timeout or self._timeout)
        except pyodbc.Error as exc:
            logger.error("SQL Server connection failed", extra={"procedure_name": procedure_name})
            raise DatabaseConnectionError("Could not connect to SQL Server") from exc
    
        try:
            with connection:
                cursor = connection.cursor()
                try:
                    # Per-cursor timeout isn't exposed by every pyodbc/unixODBC
                    # build (AttributeError on some Linux installs). The
                    # connection-level timeout passed to pyodbc.connect() above
                    # already bounds the connection attempt, so this is best-effort.
                    cursor.timeout = timeout or self._timeout
                except AttributeError:
                    pass

                try:
                    cursor.execute(sql, list(parameters))
    
                    rows: list[dict[str, Any]] = []
                    while True:
                        if cursor.description:
                            column_names = [column[0] for column in cursor.description]
                            rows.extend(
                                dict(zip(column_names, row, strict=False))
                                for row in cursor.fetchall()
                            )
                        if not cursor.nextset():
                            break
                        
                    connection.commit()
                except pyodbc.Error as exc:
                    # A THROW inside the Stored Procedure surfaces here as a
                    # driver error whose message is already a user-facing,
                    # Spanish business message (per the backend guide) -- not a
                    # technical failure. Surface it as such instead of a 503.
                    message = str(exc.args[1]) if len(exc.args) > 1 else str(exc)
                    logger.warning(
                        "Stored procedure rejected the operation",
                        extra={"procedure_name": procedure_name, "message": message},
                    )
                    raise BusinessRuleViolationError(
                        procedure_name=procedure_name, detail=message
                    ) from exc
        except DatabaseConnectionError:
            raise
        except BusinessRuleViolationError:
            raise
        except Exception as exc:  # noqa: BLE001 - last-resort safety net
            logger.error(
                "Unexpected stored procedure execution failure",
                extra={"procedure_name": procedure_name},
                exc_info=exc,
            )
            raise StoredProcedureExecutionError(procedure_name=procedure_name) from exc
    
        return StoredProcedureExecutionResult(
            row_count=len(rows),
            rows=tuple(rows),
            output_parameters={},
        )