"""Protocol and result models for the reusable stored procedure executor.

This interface keeps repository services independent from SQL Server-specific
implementation details while still providing a typed execution contract.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Protocol

from pydantic import BaseModel, ConfigDict


class StoredProcedureExecutionResult(BaseModel):
    """Typed result model produced by a stored procedure execution.

    Attributes:
        row_count: Number of rows returned by the stored procedure.
        rows: Sequence of mapped row payloads.
        output_parameters: Optional stored procedure output parameters.
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

    def execute(
        self,
        procedure_name: str,
        parameters: Mapping[str, Any] | None = None,
        *,
        timeout: int | None = None,
    ) -> StoredProcedureExecutionResult:
        """Execute a named stored procedure.

        Args:
            procedure_name: Stored procedure name.
            parameters: Optional input/output parameter mapping.
            timeout: Optional execution timeout in seconds.

        Returns:
            StoredProcedureExecutionResult: Typed result payload.
        """
