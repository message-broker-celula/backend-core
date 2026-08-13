import pytest

from app.provisioning.exceptions.provisioning_exceptions import (
    PortAllocationExhaustedError,
    PortInUseError,
)
from app.provisioning.interfaces.provisioner_client import ProvisionedContainer
from app.provisioning.services.provisioning_service import DatabaseProvisioningService
from app.repositories.exceptions.database_exceptions import BusinessRuleViolationError


class FakePortAllocator:
    """Hands out ports from a fixed, ordered sequence -- no real randomness."""

    def __init__(self, sequence: list[int]) -> None:
        self._sequence = list(sequence)

    def next_candidate(self, excluded: set[int]) -> int:
        for port in self._sequence:
            if port not in excluded:
                return port
        return -1


class FakeProvisionerClient:
    def __init__(self, fail_ports: set[int] | None = None) -> None:
        self.fail_ports = fail_ports or set()
        self.created: list[dict[str, object]] = []
        self.stopped: list[str] = []
        self.started: list[str] = []
        self.removed: list[str] = []

    def create_container(self, *, engine, version, name, host_port, database_name, username, password, root_password):
        self.created.append({"engine": engine, "host_port": host_port, "name": name})
        if host_port in self.fail_ports:
            raise PortInUseError(f"port {host_port} taken")
        return ProvisionedContainer(container_name=name, ready=True)

    def stop_container(self, name: str) -> None:
        self.stopped.append(name)

    def start_container(self, name: str) -> None:
        self.started.append(name)

    def remove_container(self, name: str) -> None:
        self.removed.append(name)


def _service(client: FakeProvisionerClient, allocator: FakePortAllocator) -> DatabaseProvisioningService:
    return DatabaseProvisioningService(
        client=client,
        port_allocator=allocator,
        public_host="db.example.com",
        supported_engines=["MYSQL"],
        password_length=24,
        port_allocation_attempts=5,
    )


def test_provision_rejects_unsupported_engine_as_business_rule_violation() -> None:
    service = _service(FakeProvisionerClient(), FakePortAllocator([30000]))

    with pytest.raises(BusinessRuleViolationError):
        service.provision(engine="POSTGRES", version="16", requested_name="db")


def test_provision_returns_real_connection_details_on_success() -> None:
    client = FakeProvisionerClient()
    service = _service(client, FakePortAllocator([30000]))

    result = service.provision(engine="MYSQL", version="8.4", requested_name="My DB")

    assert result.host == "db.example.com"
    assert result.port == 30000
    assert result.username == "app_user"
    assert result.database_name == "my_db"
    assert result.container_name == "dbinst-30000"
    assert len(client.created) == 1


def test_provision_retries_on_port_in_use_and_excludes_the_failed_port() -> None:
    client = FakeProvisionerClient(fail_ports={30000})
    service = _service(client, FakePortAllocator([30000, 30001]))

    result = service.provision(engine="MYSQL", version="8.4", requested_name="db")

    assert result.port == 30001
    assert [c["host_port"] for c in client.created] == [30000, 30001]


def test_provision_raises_when_port_allocation_exhausted() -> None:
    client = FakeProvisionerClient(fail_ports={30000})
    service = _service(client, FakePortAllocator([30000]))  # only one candidate, always taken

    with pytest.raises(PortAllocationExhaustedError):
        service.provision(engine="MYSQL", version="8.4", requested_name="db")


def test_deprovision_removes_container_derived_from_port() -> None:
    client = FakeProvisionerClient()
    service = _service(client, FakePortAllocator([30000]))

    service.deprovision(port=30000)

    assert client.removed == ["dbinst-30000"]


def test_stop_and_start_use_the_same_deterministic_container_name() -> None:
    client = FakeProvisionerClient()
    service = _service(client, FakePortAllocator([30000]))

    service.stop(port=30000)
    service.start(port=30000)

    assert client.stopped == ["dbinst-30000"]
    assert client.started == ["dbinst-30000"]
