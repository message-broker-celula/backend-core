"""Protocol and result models for the reusable stored procedure executor.

This interface keeps repository services independent from SQL Server-specific
implementation details while still providing a typed execution contract.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, Protocol

from pydantic import BaseModel, ConfigDict


class StoredProcedureExecutionResult(BaseModel):
    """Typed result model produced by a stored procedure execution.

    Attributes:
        row_count: Number of rows returned by the stored procedure.
        rows: Sequence of mapped row payloads.
        output_parameters: Reserved for the future use. OUTOUT values from Stored
            Procedures currently arrive via the trailing SELECT that each 
            procedure call issues, not via driver.level parameter binding. 
    """

    model_config = ConfigDict(extra="forbid")

    row_count: int = 0
    rows: tuple[dict[str, Any], ...] = ()
    output_parameters: dict[str, Any] = {}


class StoredProcedureExecutorProtocol(Protocol):
    """Abstract contract for executing stored procedures.

    Implementations are expected to hide SQL Server connection handling and to
    expose a business-oriented execution API to repositories.
    """

    def execute_sql(
        self,
        sql: str, 
        parameters: Sequence[Any] = (),
        *,
        procedure_name: str,
        timeout: int | None = None,


    ) -> StoredProcedureExecutionResult:
        """Execute a raw SQL statement (typically a DECLARE/EXEC/SELECT block).

        Callers own the exact SQL test so they can express named parameters, 
        OUTPUT parameters, and multi-statement blacks exactly as definied in the 
        database contract (see the backend integration guide). The executor 
        only handles connection management and result mapping. 

        Args:
            sql: Full SQL test to execute (may declare variables, call a 
                Stored Procedure with OUTPUT parameters, and SELECT the result).
            parameters: Ordered values bound ti the "?" placeholders in `sql`.
            procedure_name: Name of Stored Procedure being invoked, used 
                only for logging/error context. 
            parameters: Optional input/output parameter mapping.
            timeout: Optional execution timeout in seconds.

        Returns:
            StoredProcedureExecutionResult: Typed result payload.
        """
