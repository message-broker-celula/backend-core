"""Repository abstraction for database-centric business orchestration.

This interface remains intentionally business-oriented so services depend on
stable repository contracts rather than SQL Server details.
"""

from typing import Protocol

from app.auth.schemas.auth_schemas import (
    OAuthRegistrationResult,
    OAuthUserIdentity,
    RefreshTokenResult,
)


class DatabaseRepositoryProtocol(Protocol):
    """Reusable repository abstraction for database-backed operations.

    The repository provides business-oriented methods that route storage and
    business decisions back to the SQL Server Stored Procedure layer.
    """

    def register_oauth_user(
        self,
        provider: str,
        identity: OAuthUserIdentity,
        ip: str | None = None,
        user_agent: str | None = None,
    ) -> OAuthRegistrationResult:
        """Register an OAuth-backed user through the database layer.

        Args:
            provider: Authentication provider name.
            identity: Provider-normalized OAuth identity.

        Returns:
            OAuthRegistrationResult: Typed result from the stored procedure.
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
        """Rotate and validate a refresh token."""

    def revoke_refresh_token(self, refresh_token: str, ip: str | None = None) -> None:
        """Revoke one refresh token."""

    def revoke_all_refresh_tokens(self, subject: str, ip: str | None = None) -> None:
        """Revoke every refresh token for a subject."""

    def get_database_credentials(self, subject: str, database_id: str) -> dict[str, str]:
        """Fetch credentials for a subject from the database layer.

        Args:
            subject: Canonical subject identifier.

        Returns:
            dict[str, str]: Typed credential payload.
        """

    def register_event(
        self,
        event: str,
        subject: str | None,
        database_id: str | None,
        description: str,
        ip: str | None,
        result: str,
        additional_data: str | None = None,
    ) -> None:
        """Register a generic audit event."""
