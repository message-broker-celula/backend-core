"""Stored Procedure execution boundary contract.

Every concrete database adapter (today: SQL Server via pyodbc) implements this
protocol. Repositories depend only on this abstraction, never on pyodbc or any
other driver directly -- that is what keeps the Dependency Inversion boundary
real instead of decorative.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict


class StoredProcedureExecutionResult(BaseModel):
    """Typed envelope for a stored procedure / function execution result."""

    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    row_count: int
    rows: tuple[dict[str, Any], ...] = ()
    output_parameters: Mapping[str, Any] = {}


@runtime_checkable
class StoredProcedureExecutorProtocol(Protocol):
    """Execution contract every database adapter must satisfy."""

    def execute_sql(
        self,
        sql: str,
        parameters: Sequence[Any] = (),
        *,
        procedure_name: str,
        timeout: int | None = None,
    ) -> StoredProcedureExecutionResult:
        """Execute a stored procedure / function call and return its result."""
        ...
