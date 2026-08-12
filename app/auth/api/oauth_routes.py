"""OAuth authentication HTTP endpoints.

This module remains the HTTP-boundary for Google and GitHub authorization
handshakes. It intentionally delegates provider normalization and state
validation to the existing `OAuthService` abstraction to avoid duplicated
provider logic.
"""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import JSONResponse, RedirectResponse

from app.auth.dependencies.auth_dependencies import get_current_user
from app.auth.exceptions.auth_exceptions import AuthenticationError, OAuthStateError
from app.auth.repositories.auth_repository import AuthRepository
from app.auth.schemas.auth_schemas import (
    AccessTokenResponse,
    AuthenticatedUser,
    LogoutResponse,
    RefreshTokenRequest,
)
from app.auth.services.auth_service import AuthService
from app.auth.services.oauth_service import OAuthService
from app.core.config import settings
from app.repositories.exceptions.database_exceptions import (
    BusinessRuleViolationError,
    DatabaseIntegrationError,
)

router = APIRouter(prefix="/auth", tags=["Authentication"])
logger = logging.getLogger(__name__)

_OAUTH_STATE_COOKIE_NAME = "oauth_state"
_REFRESH_TOKEN_COOKIE_NAME = "refresh_token"
TOKEN_RESPONSE_EXAMPLE = {
    "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.example",
    "refresh_token": "refresh-token-example",
    "token_type": "bearer",
}
AUTHENTICATED_USER_EXAMPLE = {
    "subject": "user-123",
    "token_payload": {
        "sub": "user-123",
        "iat": "2026-07-23T12:00:00Z",
        "exp": "2026-07-23T13:00:00Z",
    },
}


def _cookie_key(provider: str) -> str:
    """Return the per-provider cookie key used for OAuth CSRF state.

    Args:
        provider: Provider identifier.

    Returns:
        str: Cookie key used to store the provider state value.
    """

    return f"{_OAUTH_STATE_COOKIE_NAME}_{provider}"


def get_oauth_service() -> OAuthService:
    """Return the OAuth service dependency."""

    return OAuthService()


def get_auth_service() -> AuthService:
    """Return the Stored Procedure-backed authentication service dependency."""

    return AuthService(repository=AuthRepository())


def _set_state_cookie(response: RedirectResponse, provider: str, state: str) -> None:
    """Attach the configured OAuth state cookie to a redirect response."""

    response.set_cookie(
        key=_cookie_key(provider),
        value=state,
        httponly=True,
        secure=settings.oauth.state_cookie_secure,
        samesite=settings.oauth.state_cookie_samesite,
        max_age=settings.oauth.state_ttl_seconds,
    )


def _delete_state_cookie(response: JSONResponse, provider: str) -> None:
    """Clear a provider state cookie using the configured cookie attributes."""

    response.delete_cookie(
        key=_cookie_key(provider),
        secure=settings.oauth.state_cookie_secure,
        samesite=settings.oauth.state_cookie_samesite,
    )


def _set_refresh_token_cookie(response: JSONResponse, refresh_token: str | None) -> None:
    """Attach the refresh token as an httpOnly cookie when SQL Server issued one."""

    if not refresh_token:
        return
    response.set_cookie(
        key=_REFRESH_TOKEN_COOKIE_NAME,
        value=refresh_token,
        httponly=True,
        secure=settings.oauth.state_cookie_secure,
        samesite=settings.oauth.state_cookie_samesite,
        max_age=settings.jwt.refresh_expire_minutes * 60,
    )


def _delete_refresh_token_cookie(response: JSONResponse) -> None:
    """Clear the refresh token cookie."""

    response.delete_cookie(
        key=_REFRESH_TOKEN_COOKIE_NAME,
        secure=settings.oauth.state_cookie_secure,
        samesite=settings.oauth.state_cookie_samesite,
    )


def _get_optional_current_user(
    request: Request,
    service: Annotated[AuthService, Depends(get_auth_service)],
) -> AuthenticatedUser | None:
    """Return the authenticated user if a valid bearer token is present."""

    authorization = request.headers.get("Authorization")
    if not authorization or not authorization.lower().startswith("bearer "):
        return None

    token = authorization.split(" ", 1)[1]
    try:
        return service.build_authenticated_user(token)
    except Exception:
        return None


@router.get(
    "/google",
    include_in_schema=True,
    status_code=status.HTTP_302_FOUND,
    summary="Begin Google OAuth authentication",
    description=(
        "Start the Google OAuth 2.0 authorization flow and generate a state "
        "token to prevent CSRF."
    ),
    responses={
        302: {
            "description": "Redirect to the Google authorization endpoint.",
            "headers": {"Location": {"schema": {"type": "string"}}},
        },
        500: {
            "description": "OAuth provider is not configured.",
            "content": {
                "application/json": {
                    "example": {"detail": "OAuth provider unavailable"}
                }
            },
        },
    },
)
def google_auth(
    oauth_service: Annotated[OAuthService, Depends(get_oauth_service)],
) -> RedirectResponse:
    """Redirect the browser to the Google OAuth authorization endpoint.

    Args:
    Returns:
        RedirectResponse: Redirect to the Google provider.
    """

    state = oauth_service.generate_state("google")
    try:
        redirect_url = oauth_service.build_authorization_url_with_state("google", state)
    except OAuthStateError as exc:
        logger.warning("Google OAuth start failed")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="OAuth provider unavailable",
        ) from exc

    response = RedirectResponse(url=redirect_url, status_code=status.HTTP_302_FOUND)
    _set_state_cookie(response, "google", state)
    return response


@router.get(
    "/google/callback",
    response_model=AccessTokenResponse,
    include_in_schema=True,
    summary="Complete Google OAuth callback",
    description=(
        "Validate the OAuth callback, exchange the authorization code, "
        "normalize the provider identity, and delegate JWT issuance to the "
        "auth service."
    ),
    responses={
        200: {
            "description": "JWT access token response.",
            "content": {"application/json": {"example": TOKEN_RESPONSE_EXAMPLE}},
        },
        400: {
            "description": "Invalid or denied callback.",
            "content": {
                "application/json": {
                    "example": {"detail": "Missing OAuth authorization code"}
                }
            },
        },
        401: {
            "description": "OAuth callback failed validation.",
            "content": {
                "application/json": {"example": {"detail": "Invalid OAuth state"}}
            },
        },
        502: {
            "description": "OAuth provider response failed validation.",
            "content": {
                "application/json": {
                    "example": {"detail": "OAuth provider validation failed"}
                }
            },
        },
        503: {
            "description": "Database-backed authentication is unavailable.",
            "content": {
                "application/json": {
                    "example": {"detail": "Authentication service unavailable"}
                }
            },
        },
    },
)
def google_callback(
    request: Request,
    oauth_service: Annotated[OAuthService, Depends(get_oauth_service)],
    service: Annotated[AuthService, Depends(get_auth_service)],
    code: str | None = Query(default=None),
    state: str | None = Query(default=None),
    error: str | None = Query(default=None),
) -> JSONResponse:
    """Handle the Google OAuth callback.

    Args:
        request: FastAPI request object.
        code: Provider authorization code.
        state: Provider anti-CSRF state token.
        error: Provider error flag.

    Returns:
        JSONResponse: Access token response DTO.

    Raises:
        HTTPException: When the callback state or provider exchange is invalid.
    """

    if error:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="OAuth authorization denied",
        )
    if not code:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing OAuth authorization code",
        )

    cookie_state = request.cookies.get(_cookie_key("google"))

    try:
        oauth_service.validate_state("google", state, cookie_state)
    except OAuthStateError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid OAuth state",
        ) from exc

    try:
        identity = oauth_service.exchange_code_for_identity(
            provider="google",
            code=code,
            redirect_uri=settings.oauth.google.redirect_uri,
        )
    except OAuthStateError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="OAuth provider validation failed",
        ) from exc

    try:
        response_data = service.authenticate_oauth_user(
            provider="GOOGLE",
            identity=identity,
            ip=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
        )
    except BusinessRuleViolationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=exc.detail) from exc
    except (AuthenticationError, DatabaseIntegrationError) as exc:
        logger.error("Google OAuth authentication failed", extra={"provider": "google"}, exc_info=exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication service unavailable",
        ) from exc
    response = JSONResponse(content=response_data.model_dump(mode="json"))
    _set_refresh_token_cookie(response, response_data.refresh_token)
    _delete_state_cookie(response, "google")
    return response


@router.get(
    "/github",
    include_in_schema=True,
    status_code=status.HTTP_302_FOUND,
    summary="Begin GitHub OAuth authentication",
    description="Start the GitHub OAuth flow and generate a state token for CSRF protection.",
    responses={
        302: {
            "description": "Redirect to the GitHub authorization endpoint.",
            "headers": {"Location": {"schema": {"type": "string"}}},
        },
        500: {
            "description": "OAuth provider is not configured.",
            "content": {
                "application/json": {
                    "example": {"detail": "OAuth provider unavailable"}
                }
            },
        },
    },
)
def github_auth(
    oauth_service: Annotated[OAuthService, Depends(get_oauth_service)],
) -> RedirectResponse:
    """Redirect the browser to the GitHub OAuth authorization endpoint.

    Args:
    Returns:
        RedirectResponse: Redirect to the GitHub provider.
    """

    state = oauth_service.generate_state("github")
    try:
        redirect_url = oauth_service.build_authorization_url_with_state("github", state)
    except OAuthStateError as exc:
        logger.warning("GitHub OAuth start failed")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="OAuth provider unavailable",
        ) from exc

    response = RedirectResponse(url=redirect_url, status_code=status.HTTP_302_FOUND)
    _set_state_cookie(response, "github", state)
    return response


@router.get(
    "/github/callback",
    response_model=AccessTokenResponse,
    include_in_schema=True,
    summary="Complete GitHub OAuth callback",
    description=(
        "Validate the GitHub callback, exchange the authorization code, "
        "normalize the provider identity, and delegate JWT issuance to the "
        "auth service."
    ),
    responses={
        200: {
            "description": "JWT access token response.",
            "content": {"application/json": {"example": TOKEN_RESPONSE_EXAMPLE}},
        },
        400: {
            "description": "Invalid or denied callback.",
            "content": {
                "application/json": {
                    "example": {"detail": "Missing OAuth authorization code"}
                }
            },
        },
        401: {
            "description": "OAuth callback failed validation.",
            "content": {
                "application/json": {"example": {"detail": "Invalid OAuth state"}}
            },
        },
        502: {
            "description": "OAuth provider response failed validation.",
            "content": {
                "application/json": {
                    "example": {"detail": "OAuth provider validation failed"}
                }
            },
        },
        503: {
            "description": "Database-backed authentication is unavailable.",
            "content": {
                "application/json": {
                    "example": {"detail": "Authentication service unavailable"}
                }
            },
        },
    },
)
def github_callback(
    request: Request,
    oauth_service: Annotated[OAuthService, Depends(get_oauth_service)],
    service: Annotated[AuthService, Depends(get_auth_service)],
    code: str | None = Query(default=None),
    state: str | None = Query(default=None),
    error: str | None = Query(default=None),
) -> JSONResponse:
    """Handle the GitHub OAuth callback.

    Args:
        request: FastAPI request object.
        code: Provider authorization code.
        state: Provider anti-CSRF state token.
        error: Provider error flag.

    Returns:
        JSONResponse: Access token response DTO.

    Raises:
        HTTPException: When the callback state or provider exchange is invalid.
    """

    if error:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="OAuth authorization denied",
        )
    if not code:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing OAuth authorization code",
        )

    cookie_state = request.cookies.get(_cookie_key("github"))

    try:
        oauth_service.validate_state("github", state, cookie_state)
    except OAuthStateError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid OAuth state",
        ) from exc

    try:
        identity = oauth_service.exchange_code_for_identity(
            provider="github",
            code=code,
            redirect_uri=settings.oauth.github.redirect_uri,
        )
    except OAuthStateError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="OAuth provider validation failed",
        ) from exc

    try:
        response_data = service.authenticate_oauth_user(
            provider="GITHUB",
            identity=identity,
            ip=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
        )
    except BusinessRuleViolationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=exc.detail) from exc
    except (AuthenticationError, DatabaseIntegrationError) as exc:
        logger.error("GitHub OAuth authentication failed", extra={"provider": "github"}, exc_info=exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication service unavailable",
        ) from exc
    response = JSONResponse(content=response_data.model_dump(mode="json"))
    _set_refresh_token_cookie(response, response_data.refresh_token)
    _delete_state_cookie(response, "github")
    return response


@router.get(
    "/me",
    response_model=AuthenticatedUser,
    include_in_schema=True,
    summary="Get authenticated user context",
    description=(
        "Return the current authenticated user context extracted from the "
        "validated bearer token."
    ),
    responses={
        200: {
            "description": "Authenticated user context.",
            "content": {
                "application/json": {"example": AUTHENTICATED_USER_EXAMPLE}
            },
        },
        401: {
            "description": "Missing or invalid bearer token.",
            "content": {
                "application/json": {"example": {"detail": "Invalid or expired token"}}
            },
        },
    },
)
def get_me(current_user: AuthenticatedUser = Depends(get_current_user)) -> AuthenticatedUser:
    """Return the current authenticated user context.

    Args:
        current_user: Current authenticated user dependency.

    Returns:
        AuthenticatedUser: Current user context.
    """

    return current_user


@router.post(
    "/refresh",
    response_model=AccessTokenResponse,
    include_in_schema=True,
    summary="Refresh an access token",
    description=(
        "Rotate a refresh token and issue a new access token. The returned "
        "payload contains a refreshed refresh token if the database issues one."
    ),
    responses={
        200: {
            "description": "New access token response.",
            "content": {"application/json": {"example": TOKEN_RESPONSE_EXAMPLE}},
        },
        400: {
            "description": "Missing refresh token.",
            "content": {
                "application/json": {
                    "example": {"detail": "Refresh token required"}
                }
            },
        },
        401: {
            "description": "Invalid or expired refresh token.",
            "content": {
                "application/json": {
                    "example": {"detail": "Invalid refresh token"}
                }
            },
        },
        503: {
            "description": "Authentication service unavailable.",
            "content": {
                "application/json": {
                    "example": {"detail": "Authentication service unavailable"}
                }
            },
        },
    },
)
def refresh_token(
    request: Request,
    service: Annotated[AuthService, Depends(get_auth_service)],
    refresh_request: RefreshTokenRequest | None = None,
) -> JSONResponse:
    """Rotate the provided refresh token and return a new access token."""

    token = (
        refresh_request.refresh_token
        if refresh_request is not None
        else request.cookies.get(_REFRESH_TOKEN_COOKIE_NAME)
    )
    if not token:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Refresh token required",
        )

    try:
        response_data = service.refresh_access_token(
            token,
            ip=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
        )
    except AuthenticationError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token",
        ) from exc
    except BusinessRuleViolationError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=exc.detail,
        ) from exc
    except DatabaseIntegrationError as exc:
        logger.error("Refresh token rotation failed", exc_info=exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication service unavailable",
        ) from exc

    response = JSONResponse(content=response_data.model_dump(mode="json"))
    _set_refresh_token_cookie(response, response_data.refresh_token)
    return response


@router.post(
    "/logout",
    response_model=LogoutResponse,
    include_in_schema=True,
    summary="Logout the current session",
    description=(
        "Revoke refresh token state and clear OAuth cookies. If a refresh "
        "token is provided, that token is revoked. Otherwise, the logout "
        "operation revokes all refresh tokens for the current authenticated user."
    ),
    responses={
        200: {
            "description": "Logout successful.",
            "content": {
                "application/json": {"example": {"detail": "Logged out"}}
            },
        },
        401: {
            "description": "Missing credentials or refresh token.",
            "content": {
                "application/json": {
                    "example": {"detail": "Missing logout credentials"}
                }
            },
        },
        503: {
            "description": "Authentication service unavailable.",
            "content": {
                "application/json": {
                    "example": {"detail": "Authentication service unavailable"}}
            },
        },
    },
)
def logout(
    request: Request,
    service: Annotated[AuthService, Depends(get_auth_service)],
    refresh_request: RefreshTokenRequest | None = None,
    current_user: AuthenticatedUser | None = Depends(_get_optional_current_user),
) -> JSONResponse:
    """Revoke refresh tokens and acknowledge logout."""

    try:
        cookie_refresh_token = request.cookies.get(_REFRESH_TOKEN_COOKIE_NAME)
        if refresh_request is not None:
            service.revoke_refresh_token(
                refresh_request.refresh_token,
                request.client.host if request.client else None,
            )
        elif cookie_refresh_token:
            service.revoke_refresh_token(
                cookie_refresh_token,
                request.client.host if request.client else None,
            )
        elif current_user is not None:
            service.revoke_all_refresh_tokens(
                current_user.subject,
                request.client.host if request.client else None,
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Missing logout credentials",
            )
    except AuthenticationError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token",
        ) from exc
    except BusinessRuleViolationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=exc.detail) from exc
    except DatabaseIntegrationError as exc:
        logger.error("Logout revocation failed", exc_info=exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication service unavailable",
        ) from exc

    logout_response = JSONResponse(content=LogoutResponse().model_dump())
    _delete_state_cookie(logout_response, "google")
    _delete_state_cookie(logout_response, "github")
    _delete_refresh_token_cookie(logout_response)
    return logout_response
