"""Authentication schema models.

These DTOs represent the typed boundary between the authentication foundation
and the HTTP layer.
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.core.schemas.token import TokenPayload


class AccessTokenResponse(BaseModel):
    """Response model for a bearer token issuance.

    This model intentionally exposes only the token value and token type,
    keeping the payload minimal.
    """

    model_config = ConfigDict(extra="forbid")

    access_token: str
    refresh_token: str | None = None
    token_type: Literal["bearer"] = "bearer"


class RefreshTokenRequest(BaseModel):
    """Refresh token request payload."""

    model_config = ConfigDict(extra="forbid")

    refresh_token: str


class OAuthUserIdentity(BaseModel):
    """Normalized provider identity payload.

    This DTO provides a single provider-agnostic contract for authenticated
    OAuth identities before they are passed to the service layer.
    """

    model_config = ConfigDict(extra="forbid")

    provider: str
    provider_user_id: str
    email: str | None = None
    name: str | None = None
    avatar: str | None = None
    verified_email: bool = False


class OAuthRegistrationResult(BaseModel):
    """Stored Procedure result contract returned after provider registration."""

    model_config = ConfigDict(extra="forbid")

    user_id: str
    first_login: bool | None = None
    role: str | None = None
    permissions: list[str] = Field(default_factory=list)
    refresh_token: str | None = None


class RefreshTokenResult(BaseModel):
    """Stored Procedure result returned after refresh token validation."""

    model_config = ConfigDict(extra="forbid")

    subject: str
    refresh_token: str
    role: str | None = None
    permissions: list[str] = Field(default_factory=list)


class CurrentUser(BaseModel):
    """Typed current user context extracted from a validated token."""

    model_config = ConfigDict(extra="forbid")

    subject: str
    role: str | None = None
    permissions: list[str] = Field(default_factory=list)


class LogoutResponse(BaseModel):
    """Response model returned after client logout."""

    model_config = ConfigDict(extra="forbid")

    detail: str = Field(default="Logged out")


class AuthenticatedUser(CurrentUser):
    """Authenticated user DTO containing the validated token payload."""

    token_payload: TokenPayload
