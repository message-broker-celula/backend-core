"""Célula service orchestration.

Maps Stored Procedure results into typed DTOs and derives the subdomain
addressing scheme described by the project architecture:
`[celula].<root_domain>` and `[servicio].[celula].<root_domain>`.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any

from app.celulas.interfaces.celula_repository import CelulaRepositoryProtocol
from app.celulas.schemas.celula_schemas import Celula, CelulaService, CelulaServiceType
from app.core.config import settings
from app.dns.services.dns_service import DnsProvisioningService
from app.repositories.exceptions.database_exceptions import (
    RepositoryMappingError,
    ResourceNotFoundError,
)

logger = logging.getLogger(__name__)


class CelulaOrchestrationService:
    """Coordinate célula and service orchestration for the `/celulas` API."""

    def __init__(self, repository: CelulaRepositoryProtocol, dns: DnsProvisioningService) -> None:
        """Initialize the service with a célula repository and DNS provisioning service.

        Args:
            repository: Repository adapter used to reach the Stored
                Procedure layer.
            dns: Orchestrates the real Cloudflare DNS record behind each
                célula service (see app.dns).
        """

        self._repository = repository
        self._dns = dns

    @property
    def _root_domain(self) -> str:
        return settings.app.root_domain

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
        """Register a subdomain-backed service under a célula.

        Creates the real Cloudflare DNS record first -- if sp_CrearServicio
        then rejects the create (quota, duplicate name, suspended célula,
        etc.), the just-created record is torn down instead of leaking,
        mirroring DatabaseService.create_database's compensating cleanup.
        """

        celula = self._to_celula(self._repository.get_celula(subject, celula_id))
        fqdn = self._dns.provision(service_name, celula.name)
        try:
            row = self._repository.register_celula_service(
                subject=subject,
                celula_id=celula_id,
                service_name=service_name,
                service_type=service_type.value,
                database_id=database_id,
                port=port,
                ip=ip,
            )
        except Exception:
            logger.error(
                "sp_CrearServicio failed after DNS provisioning; removing orphaned record",
                extra={"celula_id": celula_id, "service_name": service_name, "fqdn": fqdn},
            )
            try:
                self._dns.deprovision(service_name, celula.name)
            except Exception as cleanup_exc:
                logger.error("Failed to clean up orphaned DNS record", exc_info=cleanup_exc)
            raise

        logger.info(
            "Célula service registered",
            extra={"celula_id": celula_id, "service_name": service_name, "fqdn": fqdn},
        )
        return self._to_service(row, celula_id, fallback_name=service_name, fallback_type=service_type)

    def list_services(self, subject: str, celula_id: str) -> list[CelulaService]:
        """List services registered under a célula."""

        rows = self._repository.list_celula_services(subject, celula_id)
        return [self._to_service(row, celula_id) for row in rows]

    def check_dns_status(self, subject: str, celula_id: str, service_id: str) -> dict[str, bool | str]:
        """Check whether a célula service's DNS record has propagated."""

        celula, service_name = self._find_service_names(subject, celula_id, service_id)
        return self._dns.check_status(service_name, celula.name)

    def delete_service(self, subject: str, celula_id: str, service_id: str, ip: str | None = None) -> None:
        """Permanently remove a service registered under a célula.

        Removes the real DNS record first -- if that fails, the SQL row is
        left untouched and the call is safe to retry, same principle as
        DatabaseService.delete_database.
        """

        celula, service_name = self._find_service_names(subject, celula_id, service_id)
        self._dns.deprovision(service_name, celula.name)
        self._repository.delete_celula_service(subject, celula_id, service_id, ip)
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

    def _find_service_names(
        self, subject: str, celula_id: str, service_id: str
    ) -> tuple[Celula, str]:
        """Resolve a service's raw `nombre_servicio` and its célula's name.

        Needed to rebuild the exact FQDN before talking to Cloudflare --
        there is no "get single service by id" Stored Procedure, only a
        per-célula listing (fn_ServiciosPorCelula), so this searches it.
        """

        celula = self._to_celula(self._repository.get_celula(subject, celula_id))
        rows = self._repository.list_celula_services(subject, celula_id)
        for row in rows:
            data = self._normalized(row)
            row_id = str(
                data.get("service_id") or data.get("id_servicio") or data.get("servicioid")
                or data.get("id") or ""
            )
            if row_id == service_id:
                service_name = str(data.get("service_name") or data.get("nombre_servicio") or "")
                return celula, service_name
        raise ResourceNotFoundError(f"Service '{service_id}' was not found in célula '{celula_id}'")

    # ------------------------------------------------------------------
    # Row -> DTO mapping helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _normalized(row: Mapping[str, Any]) -> dict[str, Any]:
        return {str(key).lower(): value for key, value in row.items()}

    def _to_celula(self, row: Mapping[str, Any], fallback_owner: str | None = None) -> Celula:
        data = self._normalized(row)
        name = str(data.get("name") or data.get("nombre_celula") or data.get("nombre") or "")
        celula_id = str(
            data.get("celula_id") or data.get("id_celula") or data.get("celulaid") or data.get("id") or ""
        )
        domain = data.get("domain") or data.get("dominio") or data.get("subdominio_frontend") or (
            f"{name}.{self._root_domain}" if name else None
        )
        return Celula(
            celula_id=celula_id,
            name=name,
            domain=domain,
            owner_subject=data.get("owner_subject")
            or data.get("id_usuario")
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
        service_name = str(
            data.get("service_name") or data.get("nombre_servicio") or data.get("nombreservicio")
            or fallback_name or ""
        )
        celula_name = data.get("celula_name") or data.get("nombre_celula") or data.get("nombrecelula")
        type_value = str(
            data.get("service_type")
            or data.get("tipo_servicio")
            or data.get("tiposervicio")
            or (fallback_type.value if fallback_type else CelulaServiceType.OTHER.value)
        ).lower()
        try:
            service_type = CelulaServiceType(type_value)
        except ValueError:
            service_type = CelulaServiceType.OTHER

        domain = data.get("domain") or data.get("dominio") or data.get("subdominio_completo")
        if not domain and service_name and celula_name:
            # Fallback only -- sp_CrearServicio/fn_ServiciosPorCelula always
            # populate subdominio_completo via trg_Servicios_Subdominio, so
            # this rarely runs. Uses the DNS feature's own root domain
            # (coderhivex.com), not self._root_domain (andrescortes.dev,
            # the célula's own top-level domain) -- services live under a
            # different domain than células themselves.
            domain = f"{service_name}.{celula_name}.{settings.dns.root_domain}"

        return CelulaService(
            service_id=str(
                data.get("service_id") or data.get("id_servicio") or data.get("servicioid")
                or data.get("id") or ""
            ),
            celula_id=celula_id,
            service_name=service_name,
            service_type=service_type,
            domain=domain,
            database_id=data.get("database_id") or data.get("id_bd") or data.get("basedatosid"),
        )
