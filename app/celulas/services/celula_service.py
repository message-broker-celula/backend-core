"""Célula service orchestration.

Maps Stored Procedure results into typed DTOs and derives the subdomain
addressing scheme described by the project architecture:
`[celula].andrescortes.dev` and `[servicio].[celula].andrescortes.dev`.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any

from app.celulas.interfaces.celula_repository import CelulaRepositoryProtocol
from app.celulas.schemas.celula_schemas import Celula, CelulaService, CelulaServiceType
from app.core.config import settings
from app.repositories.exceptions.database_exceptions import (
    RepositoryMappingError,
    ResourceNotFoundError,
)

logger = logging.getLogger(__name__)


class CelulaOrchestrationService:
    """Coordinate célula and service orchestration for the `/celulas` API."""

    def __init__(self, repository: CelulaRepositoryProtocol) -> None:
        """Initialize the service with a célula repository."""

        self._repository = repository

    @property
    def _root_domain(self) -> str:
        return getattr(settings.app, "root_domain", "andrescortes.dev")

    def create_celula(self, subject: str, name: str, ip: str | None = None) -> Celula:
        """Create a new célula workspace owned by the subject."""

        row = self._repository.create_celula(subject, name, ip)
        logger.info("Célula created", extra={"subject": subject, "name": name})
        return self._to_celula(row, fallback_owner=subject)

    def list_celulas(self, subject: str) -> list[Celula]:
        """List célula workspaces visible to the subject."""

        rows = self._repository.list_celulas(subject)
        return [self._to_celula(row) for row in rows]

    def get_celula(self, subject: str, celula_id: str) -> Celula:
        """Fetch a single célula scoped to the requesting subject."""

        try:
            row = self._repository.get_celula(subject, celula_id)
        except RepositoryMappingError as exc:
            raise ResourceNotFoundError(f"Célula '{celula_id}' was not found") from exc
        return self._to_celula(row)

    def register_service(
        self,
        subject: str,
        celula_id: str,
        service_name: str,
        service_type: CelulaServiceType,
        database_id: str | None,
        port: int | None,
        ip: str | None,
    ) -> CelulaService:
        """Register a subdomain-backed service under a célula."""

        row = self._repository.register_celula_service(
            subject=subject,
            celula_id=celula_id,
            service_name=service_name,
            service_type=service_type.value,
            database_id=database_id,
            port=port,
            ip=ip,
        )
        logger.info(
            "Célula service registered",
            extra={"celula_id": celula_id, "service_name": service_name},
        )
        return self._to_service(row, celula_id, fallback_name=service_name, fallback_type=service_type)

    def list_services(self, subject: str, celula_id: str) -> list[CelulaService]:
        """List services registered under a célula."""

        rows = self._repository.list_celula_services(subject, celula_id)
        return [self._to_service(row, celula_id) for row in rows]

    def delete_service(self, subject: str, celula_id: str, service_id: str) -> None:
        """Remove a service registered under a célula."""

        self._repository.delete_celula_service(subject, celula_id, service_id)
        logger.info(
            "Célula service deleted",
            extra={"celula_id": celula_id, "service_id": service_id},
        )

    def change_service_status(
        self,
        subject: str,
        service_id: str,
        new_status: str,
        ip: str | None,
    ) -> None:
        """Change a service status through the database layer."""

        self._repository.change_service_status(subject, service_id, new_status, ip)

    # ------------------------------------------------------------------
    # Row -> DTO mapping helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _normalized(row: Mapping[str, Any]) -> dict[str, Any]:
        return {str(key).lower(): value for key, value in row.items()}

    def _to_celula(self, row: Mapping[str, Any], fallback_owner: str | None = None) -> Celula:
        data = self._normalized(row)
        name = str(data.get("name") or data.get("nombre") or "")
        celula_id = str(data.get("celula_id") or data.get("celulaid") or data.get("id") or "")
        domain = data.get("domain") or data.get("dominio") or (
            f"{name}.{self._root_domain}" if name else None
        )
        return Celula(
            celula_id=celula_id,
            name=name,
            domain=domain,
            owner_subject=data.get("owner_subject")
            or data.get("usuarioid")
            or fallback_owner,
        )

    def _to_service(
        self,
        row: Mapping[str, Any],
        celula_id: str,
        fallback_name: str | None = None,
        fallback_type: CelulaServiceType | None = None,
    ) -> CelulaService:
        data = self._normalized(row)
        service_name = str(data.get("service_name") or data.get("nombreservicio") or fallback_name or "")
        celula_name = data.get("celula_name") or data.get("nombrecelula")
        type_value = str(
            data.get("service_type")
            or data.get("tiposervicio")
            or (fallback_type.value if fallback_type else CelulaServiceType.OTHER.value)
        ).lower()
        try:
            service_type = CelulaServiceType(type_value)
        except ValueError:
            service_type = CelulaServiceType.OTHER

        domain = data.get("domain") or data.get("dominio")
        if not domain and service_name and celula_name:
            domain = f"{service_name}.{celula_name}.{self._root_domain}"

        return CelulaService(
            service_id=str(
                data.get("service_id") or data.get("servicioid") or data.get("id") or ""
            ),
            celula_id=celula_id,
            service_name=service_name,
            service_type=service_type,
            domain=domain,
            database_id=data.get("database_id") or data.get("basedatosid"),
        )
