"""Audit service orchestration."""

from __future__ import annotations

import json
from typing import Any

from app.audit.interfaces.audit_repository import AuditRepositoryProtocol


class AuditService:
    """Coordinate generic audit event registration."""

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
        additional_data: dict[str, Any] | str | None = None,
    ) -> None:
        """Send an audit event to SQL Server without applying business rules."""

        serialized_data = (
            json.dumps(additional_data, ensure_ascii=True)
            if isinstance(additional_data, dict)
            else additional_data
        )
        self._repository.register_event(
            event=event,
            subject=subject,
            database_id=database_id,
            description=description,
            ip=ip,
            result=result,
            additional_data=serialized_data,
        )
