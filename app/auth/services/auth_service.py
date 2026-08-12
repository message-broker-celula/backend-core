"""Authentication service orchestration.

This module is intentionally thin and delegates token issuance and validation
through the repository's existing security foundation.
"""

import logging
from collections.abc import Mapping

from app.auth.exceptions.auth_exceptions import AuthenticationError
from app.auth.interfaces.auth_repository import AuthRepositoryProtocol
from app.auth.schemas.auth_schemas import (
    AccessTokenResponse,
    AuthenticatedUser,
    OAuthRegistrationResult,
    OAuthUserIdentity,
    RefreshTokenResult,
)
from app.core.schemas.token import TokenPayload
from app.core.security import create_access_token, decode_access_token

logger = logging.getLogger(__name__)


class AuthService:
    """Coordinate authentication-related orchestration.

    The service is responsible for coordinating JWT creation and validation as
    well as shaping small DTOs for downstream FastAPI dependencies. It must not
    implement business rules or database operations directly.
    """

    def __init__(self, repository: AuthRepositoryProtocol | None = None) -> None:
        """Initialize the service with an optional repository adapter."""

        self._repository = repository

    def create_access_token_response(
        self,
        subject: str,
        additional_claims: Mapping[str, object] | None = None,
    ) -> AccessTokenResponse:
        """Create a bearer access token response."""

        token = create_access_token(
            subject=subject,
            additional_claims=dict(additional_claims) if additional_claims else None,
        )
        return AccessTokenResponse(access_token=token)

    def validate_token(self, token: str) -> TokenPayload:
        """Validate a JWT token and return its typed payload."""

        return decode_access_token(token)

    def authenticate_oauth_user(
        self,
        provider: str,
        identity: OAuthUserIdentity,
        ip: str | None = None,
        user_agent: str | None = None,
    ) -> AccessTokenResponse:
        """Orchestrate the OAuth authentication flow through the repository.

        Raises:
            AuthenticationError: When the repository contract is unavailable.
        """

        if self._repository is None:
            raise AuthenticationError("Authentication repository is not configured")

        registration_result: OAuthRegistrationResult = self._repository.register_oauth_user(
            provider=provider,
            identity=identity,
            ip=ip,
            user_agent=user_agent,
        )

        logger.info(
            "OAuth user authenticated",
            extra={"provider": provider, "subject": registration_result.user_id},
        )

        claims = {
            "provider": provider,
        }
        access_token_response = self.create_access_token_response(
            subject=registration_result.user_id,
            additional_claims={k: v for k, v in claims.items() if v is not None},
        )
        access_token_response.refresh_token = self._repository.issue_refresh_token(
            subject=registration_result.user_id,
            ip=ip,
            user_agent=user_agent,
        )

        return access_token_response

    def refresh_access_token(
        self,
        refresh_token: str,
        ip: str | None = None,
        user_agent: str | None = None,
    ) -> AccessTokenResponse:
        """Rotate an existing refresh token and return a new access token."""

        if self._repository is None:
            raise AuthenticationError("Authentication repository is not configured")

        refresh_result: RefreshTokenResult = self._repository.refresh_access_token(
            refresh_token, ip, user_agent
        )
        claims = {
            "role": refresh_result.role,
            "permissions": refresh_result.permissions,
        }
        access_token = self.create_access_token_response(
            subject=refresh_result.subject,
            additional_claims={k: v for k, v in claims.items() if v is not None},
        )
        access_token.refresh_token = refresh_result.refresh_token
        return access_token

    def revoke_refresh_token(self, refresh_token: str, ip: str | None = None) -> None:
        """Revoke a refresh token in the database."""

        if self._repository is None:
            raise AuthenticationError("Authentication repository is not configured")

        self._repository.revoke_refresh_token(refresh_token, ip)

    def revoke_all_refresh_tokens(self, subject: str, ip: str | None = None) -> None:
        """Revoke all refresh tokens for a given subject."""

        if self._repository is None:
            raise AuthenticationError("Authentication repository is not configured")

        self._repository.revoke_all_refresh_tokens(subject, ip)

    def build_authenticated_user(self, token: str) -> AuthenticatedUser:
        """Build an authenticated user DTO from a validated token."""

        payload = self.validate_token(token)
        user_data = payload.model_dump()
        return AuthenticatedUser(
            subject=payload.sub,
            role=user_data.get("role"),
            permissions=user_data.get("permissions", []),
            token_payload=payload,
        )
