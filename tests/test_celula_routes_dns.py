from fastapi.testclient import TestClient

from app.auth.dependencies.auth_dependencies import get_current_user
from app.auth.schemas.auth_schemas import AuthenticatedUser
from app.celulas.api.celula_routes import get_celula_service
from app.celulas.schemas.celula_schemas import Celula, CelulaService, CelulaServiceType
from app.core.security import create_access_token, decode_access_token
from app.main import app
from app.repositories.exceptions.database_exceptions import (
    BusinessRuleViolationError,
    ResourceNotFoundError,
)


class FakeCelulaOrchestrationService:
    def __init__(self) -> None:
        self.fail_register_with: Exception | None = None
        self.fail_delete_with: Exception | None = None
        self.dns_status: dict = {"fqdn": "api.alpha.coderhivex.com", "propagated": True}

    def register_service(self, subject, celula_id, service_name, service_type, database_id, port, ip):
        if self.fail_register_with:
            raise self.fail_register_with
        return CelulaService(
            service_id="svc-1",
            celula_id=celula_id,
            service_name=service_name,
            service_type=service_type,
            domain=f"https://{service_name}.alpha.coderhivex.com",
            database_id=database_id,
        )

    def delete_service(self, subject, celula_id, service_id, ip=None):
        if self.fail_delete_with:
            raise self.fail_delete_with

    def check_dns_status(self, subject, celula_id, service_id):
        return self.dns_status


def _client(fake_service: FakeCelulaOrchestrationService) -> TestClient:
    payload = decode_access_token(create_access_token(subject="user-1"))
    app.dependency_overrides[get_current_user] = lambda: AuthenticatedUser(
        subject="user-1", role="user", permissions=[], token_payload=payload
    )
    app.dependency_overrides[get_celula_service] = lambda: fake_service
    return TestClient(app)


def teardown_function() -> None:
    app.dependency_overrides.clear()


def test_register_service_rejects_invalid_name_before_reaching_the_service() -> None:
    # DNS-safe pattern validation happens at the Pydantic schema layer --
    # confirms invalid names never even reach CelulaOrchestrationService.
    fake_service = FakeCelulaOrchestrationService()
    client = _client(fake_service)

    response = client.post("/celulas/celula-1/services", json={"service_name": "Not_Valid!"})

    assert response.status_code == 422


def test_register_service_maps_business_rule_violation_to_400() -> None:
    fake_service = FakeCelulaOrchestrationService()
    fake_service.fail_register_with = BusinessRuleViolationError(
        procedure_name="sp_CrearServicio", detail="La celula alcanzo el limite maximo de subdominios."
    )
    client = _client(fake_service)

    response = client.post("/celulas/celula-1/services", json={"service_name": "api"})

    assert response.status_code == 400
    assert response.json()["detail"] == "La celula alcanzo el limite maximo de subdominios."


def test_register_service_succeeds_with_valid_name() -> None:
    fake_service = FakeCelulaOrchestrationService()
    client = _client(fake_service)

    response = client.post("/celulas/celula-1/services", json={"service_name": "api"})

    assert response.status_code == 201
    assert response.json()["domain"] == "https://api.alpha.coderhivex.com"


def test_delete_service_maps_resource_not_found_to_404() -> None:
    fake_service = FakeCelulaOrchestrationService()
    fake_service.fail_delete_with = ResourceNotFoundError("Service 'x' was not found")
    client = _client(fake_service)

    response = client.delete("/celulas/celula-1/services/does-not-exist")

    assert response.status_code == 404


def test_dns_status_endpoint_returns_propagation_result() -> None:
    fake_service = FakeCelulaOrchestrationService()
    client = _client(fake_service)

    response = client.get("/celulas/celula-1/services/svc-1/dns-status")

    assert response.status_code == 200
    assert response.json() == {"fqdn": "api.alpha.coderhivex.com", "propagated": True}
