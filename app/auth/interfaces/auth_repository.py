"""Authentication repository contract.

This is the "remote control" for authentication persistence: it declares WHAT
can be done (register an OAuth login, issue/rotate/revoke refresh tokens)
without knowing HOW -- no SQL Server, no pyodbc, no Stored Procedure names
appear anywhere in this file. `AuthService` depends only on this Protocol.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from app.auth.schemas.auth_schemas import (
    OAuthRegistrationResult,
    OAuthUserIdentity,
    RefreshTokenResult,
)


@runtime_checkable
class AuthRepositoryProtocol(Protocol):
    """Persistence contract for OAuth registration and refresh-token sessions."""

    def register_oauth_user(
        self,
        provider: str,
        identity: OAuthUserIdentity,
        ip: str | None = None,
        user_agent: str | None = None,
    ) -> OAuthRegistrationResult:
        """Register or update an OAuth identity, returning the internal user id."""
        ...

    def issue_refresh_token(
        self,
        subject: str,
        ip: str | None = None,
        user_agent: str | None = None,
        validity_days: int = 30,
    ) -> str:
        """Issue the first refresh token for a freshly authenticated session."""
        ...

    def refresh_access_token(
        self,
        refresh_token: str,
        ip: str | None = None,
        user_agent: str | None = None,
    ) -> RefreshTokenResult:
        """Rotate a refresh token, returning the subject and a new token."""
        ...

    def revoke_refresh_token(self, refresh_token: str, ip: str | None = None) -> None:
        """Revoke a single refresh token."""
        ...

    def revoke_all_refresh_tokens(self, subject: str, ip: str | None = None) -> None:
        """Revoke every refresh token belonging to a subject."""
        ...
