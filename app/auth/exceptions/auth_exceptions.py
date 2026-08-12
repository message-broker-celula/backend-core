"""Authentication-domain exceptions."""

from __future__ import annotations


class AuthenticationError(RuntimeError):
    """Raised when authentication cannot be completed."""


class OAuthStateError(RuntimeError):
    """Raised when an OAuth state/CSRF token or provider exchange is invalid."""
