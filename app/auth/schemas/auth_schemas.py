"""Authentication and OAuth DTOs."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from app.core.schemas.token import TokenPayload


class OAuthUserIdentity(BaseModel):
    """Normalized identity returned by a provider (Google/GitHub)."""

    model_config = ConfigDict(frozen=True)

    provider: str
    provider_user_id: str
    email: str | None = None
    name: str | None = None
    avatar: str | None = None
    verified_email: bool = False


class OAuthRegistrationResult(BaseModel):
    """Result of `sp_RegistrarOAuth`."""

    model_config = ConfigDict(frozen=True)

    user_id: str
    first_login: bool | None = None


class RefreshTokenResult(BaseModel):
    """Result of `sp_RotarRefreshToken`."""

    model_config = ConfigDict(frozen=True)

    subject: str
    refresh_token: str
    role: str | None = None
    permissions: list[str] = Field(default_factory=list)


class AccessTokenResponse(BaseModel):
    """Bearer access token response returned by the auth endpoints."""

    access_token: str
    token_type: str = "bearer"
    refresh_token: str | None = None


class AuthenticatedUser(BaseModel):
    """Typed authenticated-user context built from a validated JWT."""

    model_config = ConfigDict(frozen=True)

    subject: str
    role: str | None = None
    permissions: list[str] = Field(default_factory=list)
    token_payload: TokenPayload


class CurrentUser(BaseModel):
    """Minimal current-user context."""

    model_config = ConfigDict(frozen=True)

    subject: str


class RefreshTokenRequest(BaseModel):
    """Optional JSON body for /auth/refresh and /auth/logout."""

    refresh_token: str


class LogoutResponse(BaseModel):
    """Acknowledgement returned after logout."""

    detail: str = "Logged out"
