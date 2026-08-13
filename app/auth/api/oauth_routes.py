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


def _cookie_key(provider: str) -> str:
    """Return the per-provider cookie key used for OAuth CSRF state."""

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
    """Attach the refresh token as an httpOnly cookie when SQL Server issued one.

    Deliberately `SameSite=None` (not the `oauth_state_cookie_samesite` config
    used for the CSRF state cookie): the state cookie is only ever read back
    on the same top-level redirect chain that set it (same-origin, `Lax` is
    fine), but this cookie must be sent by the browser on a cross-subdomain
    `fetch(..., {credentials: "include"})` from the frontend's own origin
    (e.g. mbro.andrescortes.dev calling api.mbro.andrescortes.dev) -- that
    requires `SameSite=None; Secure` regardless of the state-cookie setting.
    """

    if not refresh_token:
        return
    response.set_cookie(
        key=_REFRESH_TOKEN_COOKIE_NAME,
        value=refresh_token,
        httponly=True,
        secure=True,
        samesite="none",
        max_age=settings.jwt.refresh_expire_minutes * 60,
    )


def _delete_refresh_token_cookie(response: JSONResponse) -> None:
    """Clear the refresh token cookie."""

    response.delete_cookie(
        key=_REFRESH_TOKEN_COOKIE_NAME,
        secure=True,
        samesite="none",
    )


def _frontend_success_redirect(access_token: str) -> RedirectResponse:
    """Redirect the browser back to the frontend with the access token.

    The callback is reached via a top-level browser navigation (the OAuth
    provider redirects here directly) -- the frontend's own JS never sees a
    fetch response, so the token has to travel back via redirect, not JSON.
    The frontend owns a client-side route at `{FRONTEND_URL}/auth/callback`
    that reads `access_token` from the query string, stores it in memory,
    and should immediately scrub it from the visible URL/history via
    `history.replaceState`.
    """

    url = f"{settings.app.frontend_url}/auth/callback?access_token={access_token}&token_type=bearer"
    return RedirectResponse(url=url, status_code=status.HTTP_302_FOUND)


def _frontend_error_redirect(error_code: str, description: str) -> RedirectResponse:
    """Redirect the browser back to the frontend with an error, instead of a raw API error page."""

    from urllib.parse import quote

    url = (
        f"{settings.app.frontend_url}/auth/callback"
        f"?error={quote(error_code)}&error_description={quote(description)}"
    )
    return RedirectResponse(url=url, status_code=status.HTTP_302_FOUND)


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
    status_code=status.HTTP_302_FOUND,
    summary="Begin Google OAuth authentication",
)
def google_auth(
    oauth_service: Annotated[OAuthService, Depends(get_oauth_service)],
) -> RedirectResponse:
    """Redirect the browser to the Google OAuth authorization endpoint."""

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
    summary="Complete Google OAuth callback",
    description=(
        "Reached via a top-level browser redirect from Google, not a "
        "frontend fetch call. Always responds with a 302 back to "
        "`{FRONTEND_URL}/auth/callback`, carrying either `access_token` "
        "(success) or `error`/`error_description` (failure) as query params, "
        "and sets the refresh_token cookie on success."
    ),
)
def google_callback(
    request: Request,
    oauth_service: Annotated[OAuthService, Depends(get_oauth_service)],
    service: Annotated[AuthService, Depends(get_auth_service)],
    code: str | None = Query(default=None),
    state: str | None = Query(default=None),
    error: str | None = Query(default=None),
) -> RedirectResponse:
    """Handle the Google OAuth callback."""

    if error:
        return _frontend_error_redirect("access_denied", "OAuth authorization denied")
    if not code:
        return _frontend_error_redirect("missing_code", "Missing OAuth authorization code")

    cookie_state = request.cookies.get(_cookie_key("google"))

    try:
        oauth_service.validate_state("google", state, cookie_state)
    except OAuthStateError as exc:
        logger.warning("Google OAuth state validation failed", exc_info=exc)
        return _frontend_error_redirect("invalid_state", "Invalid OAuth state")

    try:
        identity = oauth_service.exchange_code_for_identity(
            provider="google",
            code=code,
            redirect_uri=settings.oauth.google.redirect_uri,
        )
    except OAuthStateError as exc:
        logger.error("Google OAuth provider exchange failed", exc_info=exc)
        return _frontend_error_redirect("provider_error", "OAuth provider validation failed")

    try:
        response_data = service.authenticate_oauth_user(
            provider="GOOGLE",
            identity=identity,
            ip=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
        )
    except BusinessRuleViolationError as exc:
        return _frontend_error_redirect("business_rule_violation", exc.detail)
    except (AuthenticationError, DatabaseIntegrationError) as exc:
        logger.error("Google OAuth authentication failed", extra={"provider": "google"}, exc_info=exc)
        return _frontend_error_redirect("service_unavailable", "Authentication service unavailable")

    response = _frontend_success_redirect(response_data.access_token)
    _set_refresh_token_cookie(response, response_data.refresh_token)
    _delete_state_cookie(response, "google")
    return response


@router.get(
    "/github",
    status_code=status.HTTP_302_FOUND,
    summary="Begin GitHub OAuth authentication",
)
def github_auth(
    oauth_service: Annotated[OAuthService, Depends(get_oauth_service)],
) -> RedirectResponse:
    """Redirect the browser to the GitHub OAuth authorization endpoint."""

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
    summary="Complete GitHub OAuth callback",
    description=(
        "Reached via a top-level browser redirect from GitHub, not a "
        "frontend fetch call. Always responds with a 302 back to "
        "`{FRONTEND_URL}/auth/callback`, carrying either `access_token` "
        "(success) or `error`/`error_description` (failure) as query params, "
        "and sets the refresh_token cookie on success."
    ),
)
def github_callback(
    request: Request,
    oauth_service: Annotated[OAuthService, Depends(get_oauth_service)],
    service: Annotated[AuthService, Depends(get_auth_service)],
    code: str | None = Query(default=None),
    state: str | None = Query(default=None),
    error: str | None = Query(default=None),
) -> RedirectResponse:
    """Handle the GitHub OAuth callback."""

    if error:
        return _frontend_error_redirect("access_denied", "OAuth authorization denied")
    if not code:
        return _frontend_error_redirect("missing_code", "Missing OAuth authorization code")

    cookie_state = request.cookies.get(_cookie_key("github"))

    try:
        oauth_service.validate_state("github", state, cookie_state)
    except OAuthStateError as exc:
        logger.warning("GitHub OAuth state validation failed", exc_info=exc)
        return _frontend_error_redirect("invalid_state", "Invalid OAuth state")

    try:
        identity = oauth_service.exchange_code_for_identity(
            provider="github",
            code=code,
            redirect_uri=settings.oauth.github.redirect_uri,
        )
    except OAuthStateError as exc:
        logger.error("GitHub OAuth provider exchange failed", exc_info=exc)
        return _frontend_error_redirect("provider_error", "OAuth provider validation failed")

    try:
        response_data = service.authenticate_oauth_user(
            provider="GITHUB",
            identity=identity,
            ip=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
        )
    except BusinessRuleViolationError as exc:
        return _frontend_error_redirect("business_rule_violation", exc.detail)
    except (AuthenticationError, DatabaseIntegrationError) as exc:
        logger.error("GitHub OAuth authentication failed", extra={"provider": "github"}, exc_info=exc)
        return _frontend_error_redirect("service_unavailable", "Authentication service unavailable")

    response = _frontend_success_redirect(response_data.access_token)
    _set_refresh_token_cookie(response, response_data.refresh_token)
    _delete_state_cookie(response, "github")
    return response


@router.get(
    "/me",
    response_model=AuthenticatedUser,
    summary="Get authenticated user context",
)
def get_me(current_user: AuthenticatedUser = Depends(get_current_user)) -> AuthenticatedUser:
    """Return the current authenticated user context."""

    return current_user


@router.post(
    "/refresh",
    response_model=AccessTokenResponse,
    summary="Refresh an access token",
    description=(
        "Rotate a refresh token and issue a new access token. If SQL Server "
        "detects a reused (already-rotated) refresh token, it treats this as "
        "a possible token theft and revokes every session for that user -- "
        "the client must then force a fresh login, not retry silently."
    ),
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
        # Includes the reuse-detection case: sp_RotarRefreshToken revoked all
        # sessions and threw a business message -- surface it as-is so the
        # client knows to force a fresh login instead of retrying.
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
    summary="Logout the current session",
    description=(
        "Revoke refresh token state and clear OAuth cookies. If a refresh "
        "token is provided, that token is revoked. Otherwise, the logout "
        "operation revokes all refresh tokens for the current authenticated user."
    ),
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
