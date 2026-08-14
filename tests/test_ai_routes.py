from fastapi.testclient import TestClient

from app.ai.api.ai_routes import get_ai_key_service
from app.ai.schemas.ai_schemas import AiKeyIssuedResponse
from app.auth.dependencies.auth_dependencies import get_current_user
from app.auth.schemas.auth_schemas import AuthenticatedUser
from app.core.security import create_access_token, decode_access_token
from app.main import app


class FakeAiKeyService:
    def __init__(self) -> None:
        self.received_organization: str | None = "not-called"
        self.received_intended_use: str | None = "not-called"

    def issue_key(self, subject, organization, intended_use, ip):
        self.received_organization = organization
        self.received_intended_use = intended_use
        return AiKeyIssuedResponse(
            client_id=7,
            api_key="sk_live_test",
            key_prefix="sk_live_te",
            base_url="https://gateway.example.com/v1",
        )


def _client(fake_service: FakeAiKeyService) -> TestClient:
    payload = decode_access_token(create_access_token(subject="user-1"))
    app.dependency_overrides[get_current_user] = lambda: AuthenticatedUser(
        subject="user-1", role="user", permissions=[], token_payload=payload
    )
    app.dependency_overrides[get_ai_key_service] = lambda: fake_service
    return TestClient(app)


def teardown_function() -> None:
    app.dependency_overrides.clear()


def test_issue_api_key_accepts_a_fully_empty_body() -> None:
    # This is exactly how the landing app's "Generar API Key" button calls
    # it: POST /ai/api-key with no body at all. Confirmed live in
    # production this previously 422'd on "body: Field required" even
    # though every RegisterAiKeyRequest field already has a default --
    # FastAPI needs the *parameter itself* to default, same gap
    # CreateDatabaseRequest had for POST /databases.
    fake_service = FakeAiKeyService()
    client = _client(fake_service)
    token = create_access_token(subject="user-1")

    response = client.post("/ai/api-key", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 201
    assert fake_service.received_organization is None
    assert fake_service.received_intended_use is None


def test_issue_api_key_still_honors_explicit_fields() -> None:
    fake_service = FakeAiKeyService()
    client = _client(fake_service)
    token = create_access_token(subject="user-1")

    response = client.post(
        "/ai/api-key",
        json={"organization": "Equipo Alpha", "intended_use": "Clasificación de tickets"},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 201
    assert fake_service.received_organization == "Equipo Alpha"
    assert fake_service.received_intended_use == "Clasificación de tickets"
