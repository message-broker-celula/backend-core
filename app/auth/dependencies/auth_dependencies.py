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
    """Extract the subject claim from the validated token."""

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
    """Return a minimal current-user context."""

    return CurrentUser(subject=current_user.subject)


def require_subject(expected_subject: str) -> Callable[[AuthenticatedUser], AuthenticatedUser]:
    """Build an authorization dependency requiring a specific subject."""

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

    Note: this is a second, defense-in-depth layer. `sp_ListarUsuarios`,
    `sp_ActualizarRolUsuario`, and `sp_ListarTodasLasBasesDatos` already
    validate the ADMIN role themselves inside the database -- this dependency
    exists so the API rejects non-admins before ever reaching SQL Server.
    """

    def dependency(
        current_user: AuthenticatedUser = Depends(get_current_user),
    ) -> AuthenticatedUser:
        normalized_allowed_roles = {role.lower() for role in allowed_roles}
        if not current_user.role or current_user.role.lower() not in normalized_allowed_roles:
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
