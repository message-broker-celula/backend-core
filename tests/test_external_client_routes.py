from datetime import datetime, timezone

from fastapi.testclient import TestClient

from app.auth.schemas.auth_schemas import AuthenticatedUser
from app.core.schemas.token import TokenPayload
from app.databases.api.database_routes import get_database_service
from app.databases.schemas.database_schemas import (
    DatabaseActionResponse,
    DatabaseInstance,
    DatabaseStatus,
    EngineOption,
)
from app.external_clients.dependencies import get_current_external_client, get_external_client_service
from app.external_clients.schemas.external_client_schemas import ExternalClientKeyResponse
from app.main import app


class FakeExternalClientService:
    def __init__(self) -> None:
        self.registered: list[tuple] = []

    def register(self, team_name, contact_email, ip):
        self.registered.append((team_name, contact_email, ip))
        return ExternalClientKeyResponse(client_id="user-1", api_key="pgk_live_new", key_prefix="pgk_live_ne")

    def rotate(self, api_key, ip):
        return ExternalClientKeyResponse(client_id="user-1", api_key="pgk_live_rot", key_prefix="pgk_live_ro")

    def revoke(self, api_key, ip):
        pass


class FakeDatabaseService:
    def __init__(self) -> None:
        self.received_payload: dict | None = None
        self.engines = [
            EngineOption(nombre_motor="MYSQL", version_motor="8.4"),
            EngineOption(nombre_motor="POSTGRES", version_motor="16"),
        ]
        self.databases: list[DatabaseInstance] = []

    def list_available_engines(self):
        return self.engines

    def create_database(self, subject, payload, ip):
        self.received_payload = dict(payload)
        return DatabaseActionResponse(database_id="db-1", status=DatabaseStatus.ACTIVE, detail="Database created")

    def list_databases(self, subject):
        return self.databases


def _authenticated_client(client_service, db_service: FakeDatabaseService | None = None) -> TestClient:
    now = datetime.now(timezone.utc)
    app.dependency_overrides[get_current_external_client] = lambda: AuthenticatedUser(
        subject="user-1",
        role="external_client",
        permissions=[],
        token_payload=TokenPayload(sub="user-1", iat=now, exp=now),
    )
    app.dependency_overrides[get_external_client_service] = lambda: client_service
    if db_service is not None:
        app.dependency_overrides[get_database_service] = lambda: db_service
    return TestClient(app)


def teardown_function() -> None:
    app.dependency_overrides.clear()


def test_register_requires_no_auth_and_returns_the_key() -> None:
    client_service = FakeExternalClientService()
    app.dependency_overrides[get_external_client_service] = lambda: client_service
    client = TestClient(app)

    response = client.post(
        "/public/postgres/register",
        json={"team_name": "Idempotencia", "contact_email": "equipo@idempotencia.dev"},
    )

    assert response.status_code == 201
    assert response.json() == {"client_id": "user-1", "api_key": "pgk_live_new", "key_prefix": "pgk_live_ne"}
    assert client_service.registered == [("Idempotencia", "equipo@idempotencia.dev", "testclient")]


def test_register_rejects_a_malformed_email() -> None:
    client_service = FakeExternalClientService()
    app.dependency_overrides[get_external_client_service] = lambda: client_service
    client = TestClient(app)

    response = client.post(
        "/public/postgres/register",
        json={"team_name": "Idempotencia", "contact_email": "not-an-email"},
    )

    assert response.status_code == 422


def test_database_routes_require_a_bearer_api_key() -> None:
    client = TestClient(app)

    response = client.get("/public/postgres/databases")

    assert response.status_code == 401


def test_create_database_forces_the_postgres_engine_server_side() -> None:
    client_service = FakeExternalClientService()
    db_service = FakeDatabaseService()
    client = _authenticated_client(client_service, db_service)

    response = client.post(
        "/public/postgres/databases",
        json={"nombre_bd": "idempotencia_prod"},
        headers={"Authorization": "Bearer pgk_live_whatever"},
    )

    assert response.status_code == 201
    assert db_service.received_payload["nombre_motor"] == "POSTGRES"
    assert db_service.received_payload["version_motor"] == "16"
    assert db_service.received_payload["nombre_bd"] == "idempotencia_prod"


def test_list_databases_uses_the_api_key_resolved_subject() -> None:
    client_service = FakeExternalClientService()
    db_service = FakeDatabaseService()
    client = _authenticated_client(client_service, db_service)

    response = client.get("/public/postgres/databases", headers={"Authorization": "Bearer pgk_live_whatever"})

    assert response.status_code == 200
    assert response.json() == {"databases": []}


def test_metrics_aggregates_only_the_callers_own_databases() -> None:
    client_service = FakeExternalClientService()
    db_service = FakeDatabaseService()
    db_service.databases = [
        DatabaseInstance(
            database_id="db-1", status=DatabaseStatus.ACTIVE, storage_used_mb=5.0, storage_limit_mb=20.0
        ),
        DatabaseInstance(
            database_id="db-2", status=DatabaseStatus.PAUSED, storage_used_mb=2.5, storage_limit_mb=20.0
        ),
    ]
    client = _authenticated_client(client_service, db_service)

    response = client.get("/public/postgres/metrics", headers={"Authorization": "Bearer pgk_live_whatever"})

    assert response.status_code == 200
    assert response.json() == {
        "total_databases": 2,
        "active_databases": 1,
        "storage_used_mb": 7.5,
        "storage_limit_mb": 40.0,
    }


def test_metrics_requires_a_bearer_api_key() -> None:
    client = TestClient(app)

    response = client.get("/public/postgres/metrics")

    assert response.status_code == 401


def test_rotate_api_key() -> None:
    client_service = FakeExternalClientService()
    client = _authenticated_client(client_service)

    response = client.post("/public/postgres/api-key/rotate", headers={"Authorization": "Bearer pgk_live_whatever"})

    assert response.status_code == 200
    assert response.json()["api_key"] == "pgk_live_rot"


def test_revoke_api_key() -> None:
    client_service = FakeExternalClientService()
    client = _authenticated_client(client_service)

    response = client.delete("/public/postgres/api-key", headers={"Authorization": "Bearer pgk_live_whatever"})

    assert response.status_code == 200
    assert response.json() == {"detail": "API key revoked"}
