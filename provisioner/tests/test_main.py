from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.docker_client import CapacityExceededError, ContainerNotFoundError, PortInUseError
from app.main import app, get_client

settings.shared_secret = "test-secret"

_HEADERS = {"X-Internal-Token": "test-secret"}
_PAYLOAD = {
    "engine": "mysql",
    "version": "8.4",
    "name": "dbinst-1",
    "host_port": 1,
    "database_name": "db",
    "username": "u",
    "password": "p",
    "root_password": "r",
}


@pytest.fixture
def fake_client() -> MagicMock:
    fake = MagicMock()
    app.dependency_overrides[get_client] = lambda: fake
    yield fake
    app.dependency_overrides.clear()


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def test_health_requires_no_auth(client: TestClient) -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "healthy"}


def test_create_container_requires_token(client: TestClient, fake_client: MagicMock) -> None:
    # Missing required header -> FastAPI request validation (422), before
    # verify_token's own body ever runs; a *wrong* value is what exercises
    # verify_token's 401 (see test_create_container_rejects_wrong_token).
    response = client.post("/containers", json=_PAYLOAD)

    assert response.status_code == 422
    fake_client.create_container.assert_not_called()


def test_create_container_rejects_wrong_token(client: TestClient, fake_client: MagicMock) -> None:
    response = client.post("/containers", json=_PAYLOAD, headers={"X-Internal-Token": "wrong"})

    assert response.status_code == 401


def test_create_container_success(client: TestClient, fake_client: MagicMock) -> None:
    fake_client.create_container.return_value = True

    response = client.post("/containers", json=_PAYLOAD, headers=_HEADERS)

    assert response.status_code == 201
    assert response.json() == {"container_id": "dbinst-1", "ready": True}


def test_create_container_port_conflict_returns_409(client: TestClient, fake_client: MagicMock) -> None:
    fake_client.create_container.side_effect = PortInUseError("taken")

    response = client.post("/containers", json=_PAYLOAD, headers=_HEADERS)

    assert response.status_code == 409
    assert response.json()["detail"] == "port_in_use"


def test_create_container_at_capacity_returns_503(client: TestClient, fake_client: MagicMock) -> None:
    fake_client.create_container.side_effect = CapacityExceededError("At capacity")

    response = client.post("/containers", json=_PAYLOAD, headers=_HEADERS)

    assert response.status_code == 503


def test_stop_container_not_found_returns_404(client: TestClient, fake_client: MagicMock) -> None:
    fake_client.stop_container.side_effect = ContainerNotFoundError("dbinst-1")

    response = client.post("/containers/dbinst-1/stop", headers=_HEADERS)

    assert response.status_code == 404


def test_remove_container_success(client: TestClient, fake_client: MagicMock) -> None:
    response = client.delete("/containers/dbinst-1", headers=_HEADERS)

    assert response.status_code == 200
    assert response.json() == {"status": "removed"}
    fake_client.remove_container.assert_called_once_with("dbinst-1")
