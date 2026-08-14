import pytest

from app.databases.schemas.database_schemas import DatabaseStatus
from app.databases.services.database_service import DatabaseService
from app.provisioning.exceptions.provisioning_exceptions import ProvisioningError
from app.provisioning.services.provisioning_service import ProvisionedDatabase
from app.repositories.exceptions.database_exceptions import BusinessRuleViolationError


class FakeProvisioning:
    def __init__(self, provisioned: ProvisionedDatabase | None = None) -> None:
        self.provisioned = provisioned or ProvisionedDatabase(
            host="db.example.com",
            port=30000,
            username="app_user",
            password="secret",
            database_name="app_db",
            container_name="dbinst-30000",
        )
        self.provision_calls: list[dict[str, str]] = []
        self.deprovisioned: list[int] = []
        self.stopped: list[int] = []
        self.started: list[int] = []

    def provision(self, *, engine: str, version: str, requested_name: str) -> ProvisionedDatabase:
        self.provision_calls.append(
            {"engine": engine, "version": version, "requested_name": requested_name}
        )
        return self.provisioned

    def deprovision(self, *, port: int) -> None:
        self.deprovisioned.append(port)

    def stop(self, *, port: int) -> None:
        self.stopped.append(port)

    def start(self, *, port: int) -> None:
        self.started.append(port)


class FakeRepository:
    def __init__(self, database_id: str = "db-1", row: dict | None = None) -> None:
        self.database_id = database_id
        self.row = row if row is not None else {"puerto": 30000}
        self.create_payload: dict | None = None
        self.deleted = False
        self.paused = False
        self.resumed = False
        self.fail_create = False

    def create_database(self, subject, payload, ip):
        self.create_payload = payload
        if self.fail_create:
            raise BusinessRuleViolationError(procedure_name="sp_CrearBD", detail="quota exceeded")
        return self.database_id

    def get_database(self, subject, database_id):
        return self.row

    def delete_database(self, subject, database_id, ip=None):
        self.deleted = True

    def pause_database(self, subject, database_id, ip=None):
        self.paused = True

    def resume_database(self, subject, database_id, ip=None):
        self.resumed = True


def test_create_database_provisions_then_enriches_payload_before_sp_call() -> None:
    provisioning = FakeProvisioning()
    repository = FakeRepository()
    service = DatabaseService(repository=repository, provisioning=provisioning)

    response = service.create_database(
        "user-1",
        {"nombre_motor": "mysql", "version_motor": "8.4", "nombre_bd": "My DB"},
        "127.0.0.1",
    )

    assert response.database_id == "db-1"
    assert response.status == DatabaseStatus.ACTIVE
    assert repository.create_payload["host"] == "db.example.com"
    assert repository.create_payload["puerto"] == 30000
    assert repository.create_payload["usuario_bd"] == "app_user"
    assert repository.create_payload["password_bd"] == "secret"
    assert repository.create_payload["nombre_bd"] == "app_db"
    assert provisioning.provision_calls == [
        {"engine": "MYSQL", "version": "8.4", "requested_name": "My DB"}
    ]


def test_create_database_deprovisions_container_when_sp_crear_bd_rejects_it() -> None:
    provisioning = FakeProvisioning()
    repository = FakeRepository()
    repository.fail_create = True
    service = DatabaseService(repository=repository, provisioning=provisioning)

    with pytest.raises(BusinessRuleViolationError):
        service.create_database(
            "user-1",
            {"nombre_motor": "mysql", "version_motor": "8.4", "nombre_bd": "db"},
            None,
        )

    assert provisioning.deprovisioned == [30000]


def test_delete_database_removes_container_before_sp_eliminar_bd() -> None:
    provisioning = FakeProvisioning()
    repository = FakeRepository()
    service = DatabaseService(repository=repository, provisioning=provisioning)

    service.delete_database("user-1", "db-1", None)

    assert provisioning.deprovisioned == [30000]
    assert repository.deleted is True


def test_pause_database_stops_container_before_sp_pausar_bd() -> None:
    provisioning = FakeProvisioning()
    repository = FakeRepository()
    service = DatabaseService(repository=repository, provisioning=provisioning)

    service.pause_database("user-1", "db-1", None)

    assert provisioning.stopped == [30000]
    assert repository.paused is True


def test_resume_database_starts_container_before_calling_sp_reanudar_bd() -> None:
    provisioning = FakeProvisioning()
    repository = FakeRepository()
    service = DatabaseService(repository=repository, provisioning=provisioning)

    service.resume_database("user-1", "db-1")

    assert provisioning.started == [30000]
    assert repository.resumed is True


def test_delete_database_raises_when_row_has_no_port() -> None:
    provisioning = FakeProvisioning()
    repository = FakeRepository(row={})
    service = DatabaseService(repository=repository, provisioning=provisioning)

    with pytest.raises(ProvisioningError):
        service.delete_database("user-1", "db-1", None)
