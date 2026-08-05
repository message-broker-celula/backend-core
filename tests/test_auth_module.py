import unittest
from collections.abc import Mapping

from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials

from app.auth.dependencies.auth_dependencies import (
    get_current_subject,
    get_current_token,
    get_current_user,
)
from app.auth.exceptions.auth_exceptions import OAuthStateError
from app.auth.schemas.auth_schemas import (
    OAuthRegistrationResult,
    OAuthUserIdentity,
    RefreshTokenResult,
)
from app.auth.services.auth_service import AuthService
from app.auth.services.oauth_service import OAuthService
from app.core.security import create_access_token
from app.repositories.implementations.sqlserver_repository import SQLServerRepository
from app.repositories.interfaces.sp_executor import StoredProcedureExecutionResult


class FakeAuthRepository:
    def register_oauth_user(
        self,
        provider: str,
        identity: OAuthUserIdentity,
        ip: str | None = None,
        user_agent: str | None = None,
    ) -> OAuthRegistrationResult:
        self.provider = provider
        self.identity = identity
        self.ip = ip
        self.user_agent = user_agent
        return OAuthRegistrationResult(user_id="user-123")

    def provision_database(self, subject: str) -> None:
        self.provisioned_subject = subject

    def get_database_credentials(self, subject: str) -> dict[str, str]:
        return {"subject": subject}

    def issue_refresh_token(
        self,
        subject: str,
        ip: str | None = None,
        user_agent: str | None = None,
        validity_days: int = 30,
    ) -> str:
        self.issued_subject = subject
        self.issue_ip = ip
        self.issue_user_agent = user_agent
        return "issued-refresh-token"

    def refresh_access_token(
        self,
        refresh_token: str,
        ip: str | None = None,
        user_agent: str | None = None,
        validity_days: int = 30,
    ) -> RefreshTokenResult:
        self.refresh_token = refresh_token
        self.refresh_ip = ip
        self.refresh_user_agent = user_agent
        return RefreshTokenResult(
            subject="user-123",
            refresh_token="new-refresh-token",
            role="user",
            permissions=["read"],
        )

    def revoke_refresh_token(self, refresh_token: str, ip: str | None = None) -> None:
        self.revoked_token = refresh_token
        self.revoked_ip = ip

    def revoke_all_refresh_tokens(self, subject: str, ip: str | None = None) -> None:
        self.revoked_subject = subject
        self.revoked_all_ip = ip


class FakeExecutor:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, object]]] = []

    def execute_sql(
        self,
        sql: str,
        parameters: tuple[object, ...] = (),
        *,
        procedure_name: str,
        timeout: int | None = None,
    ) -> StoredProcedureExecutionResult:
        self.calls.append((procedure_name, {"sql": sql, "parameters": parameters}))
        return StoredProcedureExecutionResult(
            row_count=1,
            rows=(
                {
                    "id_usuario": "db-user-1",
                    "es_nuevo": 1,
                },
            ),
        )


class FakeOAuthHttpClient:
    def __init__(
        self,
        token_payload: Mapping[str, object],
        user_payload: Mapping[str, object],
        email_payload: list[object] | None = None,
    ) -> None:
        self.token_payload = token_payload
        self.user_payload = user_payload
        self.email_payload = email_payload or []
        self.get_urls: list[str] = []

    def post_json(
        self,
        url: str,
        data: Mapping[str, str],
        headers: Mapping[str, str] | None = None,
    ) -> Mapping[str, object]:
        self.post_url = url
        self.post_data = data
        return self.token_payload

    def get_json(
        self,
        url: str,
        headers: Mapping[str, str] | None = None,
    ) -> Mapping[str, object] | list[object]:
        self.get_urls.append(url)
        if url.endswith("/emails"):
            return self.email_payload
        return self.user_payload


class AuthServiceTests(unittest.TestCase):
    def test_authenticate_oauth_user_delegates_to_repository_and_issues_token(self) -> None:
        repository = FakeAuthRepository()
        service = AuthService(repository=repository)
        identity = OAuthUserIdentity(
            provider="google",
            provider_user_id="google-user",
            email="person@example.com",
            verified_email=True,
        )

        response = service.authenticate_oauth_user(
            provider="google",
            identity=identity,
            ip="127.0.0.1",
            user_agent="test-agent",
        )
        payload = service.validate_token(response.access_token)

        self.assertEqual(repository.provider, "google")
        self.assertEqual(repository.identity.provider_user_id, "google-user")
        self.assertEqual(repository.ip, "127.0.0.1")
        self.assertEqual(repository.user_agent, "test-agent")
        self.assertEqual(repository.issued_subject, "user-123")
        self.assertEqual(response.refresh_token, "issued-refresh-token")
        self.assertEqual(payload.sub, "user-123")

    def test_refresh_access_token_rotates_refresh_token_and_issues_new_access_token(self) -> None:
        repository = FakeAuthRepository()
        service = AuthService(repository=repository)

        response = service.refresh_access_token("refresh-token", "127.0.0.1", "test-agent")

        self.assertEqual(repository.refresh_token, "refresh-token")
        self.assertEqual(repository.refresh_ip, "127.0.0.1")
        self.assertEqual(repository.refresh_user_agent, "test-agent")
        self.assertEqual(response.refresh_token, "new-refresh-token")
        self.assertEqual(service.validate_token(response.access_token).sub, "user-123")

    def test_revoke_refresh_token_delegates_to_repository(self) -> None:
        repository = FakeAuthRepository()
        service = AuthService(repository=repository)

        service.revoke_refresh_token("refresh-token")
        self.assertEqual(repository.revoked_token, "refresh-token")

    def test_revoke_all_refresh_tokens_delegates_to_repository(self) -> None:
        repository = FakeAuthRepository()
        service = AuthService(repository=repository)

        service.revoke_all_refresh_tokens("user-123")
        self.assertEqual(repository.revoked_subject, "user-123")


class AuthDependencyTests(unittest.TestCase):
    def test_current_token_requires_bearer_credentials(self) -> None:
        with self.assertRaises(HTTPException) as raised:
            get_current_token(None)

        self.assertEqual(raised.exception.status_code, 401)

    def test_current_subject_reads_valid_jwt(self) -> None:
        token = create_access_token(subject="subject-1")
        subject = get_current_subject(token)

        self.assertEqual(subject, "subject-1")

    def test_current_user_reads_valid_jwt(self) -> None:
        token = create_access_token(subject="subject-2")
        user = get_current_user(token=token, service=AuthService())

        self.assertEqual(user.subject, "subject-2")

    def test_current_token_accepts_bearer_scheme(self) -> None:
        credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials="abc")

        self.assertEqual(get_current_token(credentials), "abc")


class OAuthServiceTests(unittest.TestCase):
    def test_validate_state_rejects_missing_or_mismatched_state(self) -> None:
        service = OAuthService()
        state = service.generate_state("google")

        with self.assertRaises(OAuthStateError):
            service.validate_state("google", state, "different")

        with self.assertRaises(OAuthStateError):
            service.validate_state("github", None, state)

    def test_validate_state_accepts_matching_state(self) -> None:
        service = OAuthService()
        state = service.generate_state("google")

        service.validate_state("google", state, state)

    def test_validate_state_rejects_unsigned_state(self) -> None:
        service = OAuthService()

        with self.assertRaises(OAuthStateError):
            service.validate_state("google", "same", "same")

    def test_exchange_google_code_normalizes_identity(self) -> None:
        http_client = FakeOAuthHttpClient(
            token_payload={"access_token": "provider-token"},
            user_payload={
                "sub": "google-user",
                "email": "person@example.com",
                "name": "Person",
                "picture": "https://example.com/avatar.png",
                "email_verified": True,
            },
        )
        service = OAuthService(http_client=http_client)

        identity = service.exchange_code_for_identity(
            provider="google",
            code="code",
            redirect_uri="http://localhost/google",
        )

        self.assertEqual(identity.provider, "google")
        self.assertEqual(identity.provider_user_id, "google-user")
        self.assertTrue(identity.verified_email)

    def test_exchange_github_code_fetches_primary_email_when_profile_email_hidden(self) -> None:
        http_client = FakeOAuthHttpClient(
            token_payload={"access_token": "provider-token"},
            user_payload={
                "id": 42,
                "login": "octocat",
                "email": None,
                "avatar_url": "https://example.com/avatar.png",
            },
            email_payload=[
                {"email": "secondary@example.com", "primary": False, "verified": True},
                {"email": "primary@example.com", "primary": True, "verified": True},
            ],
        )
        service = OAuthService(http_client=http_client)

        identity = service.exchange_code_for_identity(
            provider="github",
            code="code",
            redirect_uri="http://localhost/github",
        )

        self.assertEqual(identity.provider, "github")
        self.assertEqual(identity.provider_user_id, "42")
        self.assertEqual(identity.email, "primary@example.com")
        self.assertTrue(identity.verified_email)


class SQLServerRepositoryTests(unittest.TestCase):
    def test_register_oauth_user_executes_stored_procedure_and_maps_result(self) -> None:
        executor = FakeExecutor()
        repository = SQLServerRepository(executor=executor)
        identity = OAuthUserIdentity(provider="github", provider_user_id="42")

        result = repository.register_oauth_user(provider="github", identity=identity)

        self.assertEqual(result.user_id, "db-user-1")
        self.assertTrue(result.first_login)
        self.assertEqual(executor.calls[0][0], "sp_RegistrarOAuth")
        self.assertEqual(executor.calls[0][1]["parameters"][1], "42")


if __name__ == "__main__":
    unittest.main()
