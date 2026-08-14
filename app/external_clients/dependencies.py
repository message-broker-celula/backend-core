"""API-key authentication dependency for `/public/postgres` routes.

Machine-to-machine analog to `app.auth.dependencies.auth_dependencies` --
mirrors `get_current_user`'s shape (returns the same `AuthenticatedUser`
DTO, so every downstream route/service that already accepts a platform
user works unchanged) but resolves identity from a long-lived API key
instead of decoding a JWT.
"""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.auth.schemas.auth_schemas import AuthenticatedUser
from app.core.schemas.token import TokenPayload
from app.external_clients.exceptions.external_client_exceptions import InvalidApiKeyError
from app.external_clients.repositories.external_client_repository import (
    ExternalClientRepository,
)
from app.external_clients.services.external_client_service import ExternalClientService

_bearer_scheme = HTTPBearer(auto_error=False)


def get_external_client_service() -> ExternalClientService:
    """Return the Stored Procedure-backed external-client service dependency."""

    return ExternalClientService(repository=ExternalClientRepository())


def get_current_external_client(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
    service: ExternalClientService = Depends(get_external_client_service),
) -> AuthenticatedUser:
    """Resolve the caller's API key into an `AuthenticatedUser`-shaped identity.

    Raises:
        HTTPException: 401 when the key is missing, unknown, or revoked.
    """

    if credentials is None or credentials.scheme.lower() != "bearer" or not credentials.credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing bearer API key",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        subject = service.authenticate(credentials.credentials)
    except InvalidApiKeyError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or revoked API key",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    now = datetime.now(timezone.utc)
    return AuthenticatedUser(
        subject=subject,
        role="external_client",
        permissions=[],
        token_payload=TokenPayload(sub=subject, iat=now, exp=now),
    )
