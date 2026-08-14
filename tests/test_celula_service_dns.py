import pytest

from app.celulas.schemas.celula_schemas import CelulaServiceType
from app.celulas.services.celula_service import CelulaOrchestrationService
from app.dns.services.dns_service import DnsProvisioningService
from app.repositories.exceptions.database_exceptions import (
    BusinessRuleViolationError,
    ResourceNotFoundError,
)


class FakeDnsClient:
    def __init__(self) -> None:
        self.created: list[tuple[str, str]] = []
        self.deleted: list[str] = []

    def record_exists(self, fqdn: str) -> bool:
        return any(f == fqdn for f, _ in self.created) and fqdn not in self.deleted

    def create_record(self, fqdn: str, target_ip: str) -> str:
        self.created.append((fqdn, target_ip))
        return "record-id-123"

    def delete_record(self, fqdn: str) -> None:
        self.deleted.append(fqdn)


class FakeCelulaRepository:
    def __init__(self) -> None:
        self.celula_row = {"id_celula": "celula-1", "nombre_celula": "alpha"}
        self.service_rows: list[dict] = [
            {"id_servicio": "svc-1", "id_celula": "celula-1", "nombre_servicio": "api"}
        ]
        self.fail_register = False
        self.deleted_service_id: str | None = None
        self.deleted_ip: str | None = None

    def get_celula(self, subject, celula_id):
        return self.celula_row

    def register_celula_service(self, subject, celula_id, service_name, service_type, database_id, port=None, ip=None):
        if self.fail_register:
            raise BusinessRuleViolationError(procedure_name="sp_CrearServicio", detail="celula suspendida")
        return {
            "id_servicio": "svc-new",
            "id_celula": celula_id,
            "nombre_servicio": service_name,
            "subdominio_completo": f"https://{service_name}.alpha.coderhivex.com",
            "estado": "ACTIVO",
        }

    def list_celula_services(self, subject, celula_id):
        return tuple(self.service_rows)

    def delete_celula_service(self, subject, celula_id, service_id, ip=None):
        self.deleted_service_id = service_id
        self.deleted_ip = ip


def _service(repository: FakeCelulaRepository, dns_client: FakeDnsClient) -> CelulaOrchestrationService:
    dns = DnsProvisioningService(client=dns_client, root_domain="coderhivex.com", target_ip="46.224.97.85")
    return CelulaOrchestrationService(repository=repository, dns=dns)


def test_register_service_creates_dns_record_before_sql_row() -> None:
    repository = FakeCelulaRepository()
    dns_client = FakeDnsClient()
    service = _service(repository, dns_client)

    result = service.register_service(
        subject="user-1",
        celula_id="celula-1",
        service_name="api2",
        service_type=CelulaServiceType.API,
        database_id=None,
        port=8080,
        ip=None,
    )

    assert dns_client.created == [("api2.alpha.coderhivex.com", "46.224.97.85")]
    assert result.domain == "https://api2.alpha.coderhivex.com"


def test_register_service_cleans_up_dns_record_when_sql_rejects_it() -> None:
    repository = FakeCelulaRepository()
    repository.fail_register = True
    dns_client = FakeDnsClient()
    service = _service(repository, dns_client)

    with pytest.raises(BusinessRuleViolationError):
        service.register_service(
            subject="user-1",
            celula_id="celula-1",
            service_name="api2",
            service_type=CelulaServiceType.API,
            database_id=None,
            port=8080,
            ip=None,
        )

    assert dns_client.deleted == ["api2.alpha.coderhivex.com"]


def test_delete_service_removes_dns_record_before_sql_delete() -> None:
    repository = FakeCelulaRepository()
    dns_client = FakeDnsClient()
    service = _service(repository, dns_client)

    service.delete_service("user-1", "celula-1", "svc-1", ip="127.0.0.1")

    assert dns_client.deleted == ["api.alpha.coderhivex.com"]
    assert repository.deleted_service_id == "svc-1"
    assert repository.deleted_ip == "127.0.0.1"


def test_delete_service_raises_not_found_for_unknown_service_id() -> None:
    repository = FakeCelulaRepository()
    dns_client = FakeDnsClient()
    service = _service(repository, dns_client)

    with pytest.raises(ResourceNotFoundError):
        service.delete_service("user-1", "celula-1", "does-not-exist")

    assert dns_client.deleted == []


def test_check_dns_status_reports_propagation_for_the_right_fqdn() -> None:
    repository = FakeCelulaRepository()
    dns_client = FakeDnsClient()
    service = _service(repository, dns_client)

    result = service.check_dns_status("user-1", "celula-1", "svc-1")

    assert result == {"fqdn": "api.alpha.coderhivex.com", "propagated": False}


def test_check_dns_status_reports_propagated_true_once_the_record_exists() -> None:
    repository = FakeCelulaRepository()
    dns_client = FakeDnsClient()
    dns_client.created.append(("api.alpha.coderhivex.com", "46.224.97.85"))
    service = _service(repository, dns_client)

    result = service.check_dns_status("user-1", "celula-1", "svc-1")

    assert result == {"fqdn": "api.alpha.coderhivex.com", "propagated": True}
