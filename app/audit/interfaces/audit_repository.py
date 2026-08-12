"""Audit repository contract."""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class AuditRepositoryProtocol(Protocol):
    """Persistence contract for generic audit events (sp_RegistrarEvento)."""

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
        """Register a generic application event in the audit trail."""
        ...
