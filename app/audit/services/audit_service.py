"""Audit service orchestration."""

from __future__ import annotations

from app.audit.interfaces.audit_repository import AuditRepositoryProtocol


class AuditService:
    """Coordinate generic audit-event orchestration for the `/audit` API."""

    def __init__(self, repository: AuditRepositoryProtocol) -> None:
        self._repository = repository

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
        """Register a generic application event through sp_RegistrarEvento."""

        self._repository.register_event(
            event=event,
            subject=subject,
            database_id=database_id,
            description=description,
            ip=ip,
            result=result,
            additional_data=additional_data,
        )
