import pytest

from app.dns.services.dns_service import DnsProvisioningService, is_valid_dns_label
from app.repositories.exceptions.database_exceptions import BusinessRuleViolationError


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


def _service(client: FakeDnsClient) -> DnsProvisioningService:
    return DnsProvisioningService(client=client, root_domain="coderhivex.com", target_ip="46.224.97.85")


def test_is_valid_dns_label_accepts_lowercase_alphanumeric_and_hyphens() -> None:
    assert is_valid_dns_label("api")
    assert is_valid_dns_label("api-2")
    assert is_valid_dns_label("a")


def test_is_valid_dns_label_rejects_invalid_forms() -> None:
    assert not is_valid_dns_label("")
    assert not is_valid_dns_label("-api")
    assert not is_valid_dns_label("api-")
    assert not is_valid_dns_label("API")
    assert not is_valid_dns_label("api_2")
    assert not is_valid_dns_label("a" * 64)


def test_build_fqdn_combines_service_celula_and_root_domain() -> None:
    service = _service(FakeDnsClient())

    assert service.build_fqdn("api", "alpha") == "api.alpha.coderhivex.com"


def test_provision_creates_record_and_returns_fqdn() -> None:
    client = FakeDnsClient()
    service = _service(client)

    fqdn = service.provision("api", "alpha")

    assert fqdn == "api.alpha.coderhivex.com"
    assert client.created == [("api.alpha.coderhivex.com", "46.224.97.85")]


def test_provision_rejects_invalid_name_as_business_rule_violation() -> None:
    client = FakeDnsClient()
    service = _service(client)

    with pytest.raises(BusinessRuleViolationError):
        service.provision("Not_Valid!", "alpha")

    assert client.created == []


def test_deprovision_removes_the_record_for_the_built_fqdn() -> None:
    client = FakeDnsClient()
    service = _service(client)

    service.deprovision("api", "alpha")

    assert client.deleted == ["api.alpha.coderhivex.com"]


def test_check_status_reports_propagated_true_once_the_record_exists() -> None:
    client = FakeDnsClient()
    service = _service(client)
    service.provision("api", "alpha")

    result = service.check_status("api", "alpha")

    assert result == {"fqdn": "api.alpha.coderhivex.com", "propagated": True}


def test_check_status_reports_propagated_false_when_no_record_exists() -> None:
    client = FakeDnsClient()
    service = _service(client)

    result = service.check_status("api", "alpha")

    assert result == {"fqdn": "api.alpha.coderhivex.com", "propagated": False}
