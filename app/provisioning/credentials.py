"""Credential generation for auto-provisioned database engine containers.

Each provisioned instance is its own dedicated, single-tenant container, so
identifiers don't need global uniqueness -- only the secrets need entropy.
Uses stdlib `secrets` only; no new dependency.
"""

from __future__ import annotations

import re
import secrets

_SANITIZE_PATTERN = re.compile(r"[^a-z0-9_]")
_MAX_DATABASE_NAME_LENGTH = 40
_DEFAULT_DATABASE_NAME = "app_db"
_APP_USERNAME = "app_user"


def generate_username() -> str:
    """Return the fixed application username.

    Scoped to a single-tenant container, so a fixed value carries zero
    collision risk and avoids inventing an identifier-validation scheme
    against unknown SQL Server column widths.
    """

    return _APP_USERNAME


def sanitize_database_name(requested_name: str) -> str:
    """Sanitize a client-supplied database name into a safe MySQL identifier."""

    lowered = requested_name.strip().lower()
    sanitized = _SANITIZE_PATTERN.sub("_", lowered).strip("_")
    sanitized = sanitized[:_MAX_DATABASE_NAME_LENGTH].strip("_")
    return sanitized or _DEFAULT_DATABASE_NAME


def generate_password(length: int) -> str:
    """Return a URL-safe random secret suitable for `IDENTIFIED BY` and env vars."""

    return secrets.token_urlsafe(length)
