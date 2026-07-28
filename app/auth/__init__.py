"""Authentication foundation package.

This package provides the thin orchestration layer for future API
authentication, JWT validation, and Stored Procedure-backed identity flows.
"""

from app.auth.services.auth_service import AuthService

__all__ = ["AuthService"]
