"""Reusable SQL Server stored procedure executor.

This module is the only concrete database gateway in the backend. It keeps
connection management, parameter binding, and error sanitization in one place
so future modules can reuse the same execution contract without duplicating
connection logic.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any

from pydantic import SecretStr

from app.core.config import settings
from app.repositories.exceptions.database_exceptions import (
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

    def execute(
        self,
        procedure_name: str,
        parameters: Mapping[str, Any] | None = None,
        *,
        timeout: int | None = None,
    ) -> StoredProcedureExecutionResult:
        """Execute a stored procedure through the SQL Server execution boundary.

        Args:
            procedure_name: Name of the stored procedure to invoke.
            parameters: Optional parameter dictionary.
            timeout: Optional timeout override in seconds.

        Returns:
            StoredProcedureExecutionResult: Typed execution result.

        Raises:
            DatabaseConnectionError: When the SQL Server driver or connection is unavailable.
            StoredProcedureExecutionError: When SQL Server rejects the procedure call.
        """

        parameter_count = len(parameters or {})
        logger.info(
            "Executing stored procedure",
            extra={"procedure_name": procedure_name, "parameter_count": parameter_count},
        )

        connection_string = self._connection_string.get_secret_value()
        if not connection_string:
            raise DatabaseConnectionError("SQL Server connection string is not configured")

        try:
            import pyodbc
        except ImportError as exc:
            raise DatabaseConnectionError("SQL Server driver dependency is not installed") from exc

        try:
            with pyodbc.connect(connection_string, timeout=timeout or self._timeout) as connection:
                cursor = connection.cursor()
                cursor.timeout = timeout or self._timeout
                ordered_values = list((parameters or {}).values())
                parameter_markers = ", ".join("?" for _ in ordered_values)
                call_sql = f"{{CALL {procedure_name}({parameter_markers})}}"
                if not ordered_values:
                    call_sql = f"{{CALL {procedure_name}}}"

                cursor.execute(call_sql, ordered_values)

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
            logger.error(
                "Stored procedure execution failed",
                extra={"procedure_name": procedure_name},
            )
            raise StoredProcedureExecutionError(procedure_name=procedure_name) from exc

        return StoredProcedureExecutionResult(
            row_count=len(rows),
            rows=tuple(rows),
            output_parameters={},
        )
