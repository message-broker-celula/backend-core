from urllib.parse import parse_qs, urlparse

from fastapi.testclient import TestClient

from app.auth.api.oauth_routes import get_auth_service, get_oauth_service
from app.auth.schemas.auth_schemas import AccessTokenResponse, OAuthUserIdentity
from app.core.config import settings
from app.main import app


class FakeOAuthService:
    def validate_state(self, provider, state, cookie_state):
        return None

    def exchange_code_for_identity(self, provider, code, redirect_uri):
        return OAuthUserIdentity(provider=provider, provider_user_id="fake-user")


class FakeAuthService:
    def authenticate_oauth_user(self, provider, identity, ip=None, user_agent=None):
        return AccessTokenResponse(access_token="fake-access-token", refresh_token="fake-refresh-token")


def _client() -> TestClient:
    app.dependency_overrides[get_oauth_service] = lambda: FakeOAuthService()
    app.dependency_overrides[get_auth_service] = lambda: FakeAuthService()
    return TestClient(app, follow_redirects=False)


def teardown_function() -> None:
    app.dependency_overrides.clear()


def test_successful_callback_redirects_to_frontend_with_access_token() -> None:
    client = _client()

    response = client.get(
        "/auth/google/callback",
        params={"code": "provider-code", "state": "irrelevant-because-fake-service"},
        cookies={"oauth_state_google": "irrelevant-because-fake-service"},
    )

    assert response.status_code == 302
    location = response.headers["location"]
    parsed = urlparse(location)
    query = parse_qs(parsed.query)

    assert f"{parsed.scheme}://{parsed.netloc}" == settings.app.frontend_url
    assert parsed.path == "/auth/callback"
    assert query["access_token"] == ["fake-access-token"]
    assert query["token_type"] == ["bearer"]

    set_cookie = response.headers.get("set-cookie", "").lower()
    assert "refresh_token=fake-refresh-token" in set_cookie
    assert "samesite=none" in set_cookie
    assert "secure" in set_cookie


def test_missing_code_redirects_to_frontend_with_error() -> None:
    client = _client()

    response = client.get("/auth/github/callback")

    assert response.status_code == 302
    query = parse_qs(urlparse(response.headers["location"]).query)
    assert query["error"] == ["missing_code"]
