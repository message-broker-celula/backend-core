"""Authentication repository protocol.

This interface defines the minimal Stored Procedure orchestration contract that
future authentication providers will implement. The backend must keep the SQL
and business-rule decisions in the database layer.
"""

from typing import Protocol

from app.auth.schemas.auth_schemas import (
    OAuthRegistrationResult,
    OAuthUserIdentity,
    RefreshTokenResult,
)


class AuthRepositoryProtocol(Protocol):
    """Protocol for Stored Procedure-backed authentication orchestration.

    Repository implementations are expected to be thin adapters over database
    Stored Procedures and are intentionally limited to identity-related data
    access. No business validation should live in this interface.
    """

    def register_oauth_user(
        self,
        provider: str,
        identity: OAuthUserIdentity,
        ip: str | None = None,
        user_agent: str | None = None,
    ) -> OAuthRegistrationResult:
        """Register a provider-backed identity.

        Args:
            provider: OAuth provider name.
            identity: Provider-normalized OAuth identity.

        Returns:
            OAuthRegistrationResult: Stored Procedure result contract containing
                the generated user id and first-login flag.

        """

    def issue_refresh_token(
        self,
        subject: str,
        ip: str | None = None,
        user_agent: str | None = None,
        validity_days: int = 30,
    ) -> str:
        """Issue the first refresh token for an authenticated session."""

    def refresh_access_token(
        self,
        refresh_token: str,
        ip: str | None = None,
        user_agent: str | None = None,
        validity_days: int = 30,
    ) -> RefreshTokenResult:
        """Rotate and validate a refresh token through the database layer.

        Args:
            refresh_token: Refresh token provided by the client.

        Returns:
            RefreshTokenResult: Result containing a new refresh token and subject.
        """

    def revoke_refresh_token(self, refresh_token: str, ip: str | None = None) -> None:
        """Revoke a refresh token in the database.

        Args:
            refresh_token: Refresh token to invalidate.
        """

    def revoke_all_refresh_tokens(self, subject: str, ip: str | None = None) -> None:
        """Revoke all refresh tokens for a specific subject.

        Args:
            subject: Canonical subject identifier.
        """
