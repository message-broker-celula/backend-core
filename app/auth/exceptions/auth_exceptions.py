"""Reusable authentication exceptions.

These exceptions keep security-sensitive failures typed and consistent across
FastAPI dependencies and future auth flows.
"""


class AuthenticationError(Exception):
    """Base exception for authentication failures."""


class InvalidTokenError(AuthenticationError):
    """Raised when a bearer token cannot be decoded or validated."""


class ExpiredTokenError(InvalidTokenError):
    """Raised when a bearer token has expired."""


class UnauthorizedError(AuthenticationError):
    """Raised when a request is missing valid credentials."""


class ForbiddenError(AuthenticationError):
    """Raised when a request is authenticated but not allowed to proceed."""


class OAuthStateError(AuthenticationError):
    """Raised when an OAuth state or flow context is invalid."""
