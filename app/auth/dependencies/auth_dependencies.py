"""Authentication dependencies.

These dependencies provide the request-scoped boundary for current-user
extraction and token validation while reusing the existing JWT decoder.
"""

from collections.abc import Callable

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.auth.schemas.auth_schemas import AuthenticatedUser, CurrentUser
from app.auth.services.auth_service import AuthService
from app.core.security import decode_access_token

bearer_scheme = HTTPBearer(auto_error=False)


def get_auth_service() -> AuthService:
    """Return the request-scoped authentication service."""

    return AuthService()


def get_current_token(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> str:
    """Return the bearer token value from the request.

    Args:
        credentials: Parsed authorization credentials from the request.

    Returns:
        str: Raw token string.

    Raises:
        HTTPException: When the Authorization header is missing or invalid.
    """

    if credentials is None or credentials.scheme.lower() != "bearer" or not credentials.credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing bearer token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return credentials.credentials


def get_current_subject(token: str = Depends(get_current_token)) -> str:
    """Extract the subject claim from the validated token.

    Args:
        token: Encoded JWT value.

    Returns:
        str: Subject identifier.

    Raises:
        HTTPException: When the token payload cannot be validated.
    """

    try:
        payload = decode_access_token(token)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    return payload.sub


def get_current_user(
    token: str = Depends(get_current_token),
    service: AuthService = Depends(get_auth_service),
) -> AuthenticatedUser:
    """Return the current authenticated user as a typed DTO.

    Args:
        token: Encoded JWT value.
        service: Auth service used for orchestration.

    Returns:
        AuthenticatedUser: Typed authentication context.

    Raises:
        HTTPException: When the token is invalid.
    """

    try:
        return service.build_authenticated_user(token)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc


def get_current_user_context(
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> CurrentUser:
    """Return a minimal current-user context.

    Args:
        current_user: Authenticated DTO from the auth dependency layer.

    Returns:
        CurrentUser: Minimal user context.
    """

    return CurrentUser(subject=current_user.subject)


def require_subject(expected_subject: str) -> Callable[[AuthenticatedUser], AuthenticatedUser]:
    """Build an authorization dependency requiring a specific subject.

    Args:
        expected_subject: Subject allowed to access the protected operation.

    Returns:
        Callable[[AuthenticatedUser], AuthenticatedUser]: FastAPI dependency.
    """

    def dependency(
        current_user: AuthenticatedUser = Depends(get_current_user),
    ) -> AuthenticatedUser:
        if current_user.subject != expected_subject:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Forbidden",
            )
        return current_user

    return dependency


def require_role(*allowed_roles: str) -> Callable[[AuthenticatedUser], AuthenticatedUser]:
    """Build an authorization dependency requiring one of the allowed roles.

    Args:
        allowed_roles: Roles permitted to access the protected operation.

    Returns:
        Callable[[AuthenticatedUser], AuthenticatedUser]: FastAPI dependency.
    """

    def dependency(
        current_user: AuthenticatedUser = Depends(get_current_user),
    ) -> AuthenticatedUser:
        if not current_user.role or current_user.role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Forbidden",
            )
        return current_user

    return dependency


def ensure_authenticated(
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> AuthenticatedUser:
    """Authorization dependency requiring any authenticated subject."""

    if not current_user.subject:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden",
        )
    return current_user
