from fastapi.testclient import TestClient

from app.auth.dependencies.auth_dependencies import get_current_user
from app.auth.schemas.auth_schemas import AuthenticatedUser
from app.core.security import create_access_token, decode_access_token
from app.databases.api.database_routes import get_database_service
from app.databases.schemas.database_schemas import DatabaseActionResponse, DatabaseStatus
from app.main import app


class FakeDatabaseService:
    def __init__(self) -> None:
        self.received_payload: dict | None = None

    def create_database(self, subject, payload, ip):
        self.received_payload = dict(payload)
        return DatabaseActionResponse(
            database_id="db-1", status=DatabaseStatus.ACTIVE, detail="Database created"
        )


def _client(fake_service: FakeDatabaseService) -> TestClient:
    payload = decode_access_token(create_access_token(subject="user-1"))
    app.dependency_overrides[get_current_user] = lambda: AuthenticatedUser(
        subject="user-1", role="user", permissions=[], token_payload=payload
    )
    app.dependency_overrides[get_database_service] = lambda: fake_service
    return TestClient(app)


def teardown_function() -> None:
    app.dependency_overrides.clear()


def test_create_database_accepts_a_fully_empty_body() -> None:
    # This is exactly how the landing app's post-login auto-provisioning
    # call works (useProvisioning.ts -> provisionDatabase(token)): no
    # engine/version/name picker in the UI, POST /databases with no body
    # at all. Confirmed live in production this previously 422'd.
    fake_service = FakeDatabaseService()
    client = _client(fake_service)
    token = create_access_token(subject="user-1")

    response = client.post("/databases", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 201
    assert fake_service.received_payload["nombre_motor"] == "MYSQL"
    assert fake_service.received_payload["version_motor"] == "8.4"
    assert fake_service.received_payload["nombre_bd"] == ""


def test_create_database_still_honors_explicit_fields() -> None:
    fake_service = FakeDatabaseService()
    client = _client(fake_service)
    token = create_access_token(subject="user-1")

    response = client.post(
        "/databases",
        json={"nombre_bd": "custom_name"},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 201
    assert fake_service.received_payload["nombre_bd"] == "custom_name"
    assert fake_service.received_payload["nombre_motor"] == "MYSQL"
