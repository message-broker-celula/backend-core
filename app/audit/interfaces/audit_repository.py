"""Audit repository protocol."""

from __future__ import annotations

from typing import Protocol


class AuditRepositoryProtocol(Protocol):
    """Protocol for generic audit events."""

    def register_event(
        self,
        event: str,
        subject: str | None,
        database_id: str | None,
        description: str,
        ip: str | None,
        result: str,
        additional_data: str | None = None,
    ) -> None:
        """Register an event through sp_RegistrarEvento."""
