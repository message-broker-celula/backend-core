"""External-client (machine-to-machine) service orchestration.

Stays intentionally thin, per the project's database-centric architecture:
quotas, uniqueness, and key lifecycle rules all live in the stored
procedures this module calls. This service only shapes rows into typed
DTOs and translates "key not found" into a clean 401 at the API boundary.
"""

from __future__ import annotations

import logging

from app.external_clients.exceptions.external_client_exceptions import InvalidApiKeyError
from app.external_clients.interfaces.external_client_repository import (
    ExternalClientRepositoryProtocol,
)
from app.external_clients.schemas.external_client_schemas import ExternalClientKeyResponse

logger = logging.getLogger(__name__)


class ExternalClientService:
    """Coordinate external-client registration and API-key lifecycle."""

    def __init__(self, repository: ExternalClientRepositoryProtocol) -> None:
        self._repository = repository

    def register(self, team_name: str, contact_email: str, ip: str | None) -> ExternalClientKeyResponse:
        """Register a new external client and return its raw API key (shown once)."""

        row = self._repository.register_external_client(team_name, contact_email, ip)
        logger.info("External client registered", extra={"team_name": team_name})
        return self._to_key_response(row)

    def authenticate(self, api_key: str) -> str:
        """Resolve an API key to its shadow subject (id_usuario).

        Raises:
            InvalidApiKeyError: When the key is missing, unknown, or revoked.
        """

        subject = self._repository.validate_api_key(api_key)
        if not subject:
            raise InvalidApiKeyError("Invalid or revoked API key")
        return subject

    def rotate(self, api_key: str, ip: str | None) -> ExternalClientKeyResponse:
        """Invalidate the current key and issue a new one."""

        row = self._repository.rotate_api_key(api_key, ip)
        logger.info("External client API key rotated")
        return self._to_key_response(row)

    def revoke(self, api_key: str, ip: str | None) -> None:
        """Revoke the current key."""

        self._repository.revoke_api_key(api_key, ip)
        logger.info("External client API key revoked")

    @staticmethod
    def _to_key_response(row) -> ExternalClientKeyResponse:
        data = {str(key).lower(): value for key, value in row.items()}
        return ExternalClientKeyResponse(
            client_id=str(data["id_usuario"]),
            api_key=str(data["api_key"]),
            key_prefix=str(data["key_prefix"]),
        )
