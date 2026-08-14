"""AI Gateway key orchestration.

Coordinates the Ollama Gateway (external, already-built service) and SQL
Server's encrypted ClavesIA storage into an issue/status/rotate/revoke/
usage surface -- SQL Server is the source of truth for "does this user
have an active key," the gateway is the source of truth for limits/usage.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any

from app.ai.exceptions.ai_exceptions import AiGatewayAuthError
from app.ai.interfaces.ai_gateway_client import AiGatewayClientProtocol
from app.ai.interfaces.ai_key_repository import AiKeyRepositoryProtocol
from app.ai.schemas.ai_schemas import (
    AiKeyIssuedResponse,
    AiKeyStatusResponse,
    AiUsageResponse,
)
from app.repositories.exceptions.database_exceptions import BusinessRuleViolationError

logger = logging.getLogger(__name__)


class AiKeyService:
    """Coordinate AI Gateway key orchestration for the `/ai` API."""

    def __init__(
        self,
        repository: AiKeyRepositoryProtocol,
        gateway: AiGatewayClientProtocol,
        gateway_base_url: str,
    ) -> None:
        """Initialize the service with its repository and gateway client."""

        self._repository = repository
        self._gateway = gateway
        self._gateway_base_url = gateway_base_url

    def issue_key(
        self,
        subject: str,
        organization: str | None,
        intended_use: str | None,
        ip: str | None = None,
    ) -> AiKeyIssuedResponse:
        """Register a new gateway client for the caller and persist the key encrypted.

        Registers with the gateway first (real external resource), then
        persists -- if sp_RegistrarClaveIA rejects it (an active key
        already exists), there's nothing to clean up on the gateway side
        (unlike Cloudflare/MySQL, the gateway has no delete endpoint, and a
        stray extra registration there is harmless/inert, not a leaked
        resource with a cost).
        """

        profile = self._normalized(self._repository.get_user_profile(subject))
        name = str(profile.get("nombre") or "Usuario")
        email = str(profile.get("correo") or "")

        credential = self._gateway.register(
            name=name,
            email=email,
            organization=organization,
            intended_use=intended_use,
        )
        self._repository.register_ai_key(
            subject,
            credential.client_id,
            credential.key_prefix,
            credential.api_key,
            ip,
        )
        logger.info(
            "AI Gateway key issued",
            extra={"subject": subject, "key_prefix": credential.key_prefix},
        )
        return AiKeyIssuedResponse(
            client_id=credential.client_id,
            api_key=credential.api_key,
            key_prefix=credential.key_prefix,
            base_url=f"{self._gateway_base_url}/v1",
        )

    def get_status(self, subject: str) -> AiKeyStatusResponse:
        """Return the caller's own key status/limits, proxied from the gateway.

        Raises:
            BusinessRuleViolationError: When the caller has no active key
                (sp_ObtenerClaveIA's own THROW).
        """

        row = self._normalized(self._repository.get_ai_key(subject))
        api_key = str(row["api_key"])

        try:
            status = self._gateway.get_status(api_key)
        except AiGatewayAuthError:
            # Our record says ACTIVA but the gateway no longer honors this
            # key (revoked upstream, outside this platform's control) --
            # surface that plainly instead of a generic 503.
            raise BusinessRuleViolationError(
                procedure_name="ai_gateway_status",
                detail="La clave de IA ya no es valida en el gateway. Rotala.",
            ) from None

        return AiKeyStatusResponse(
            client_id=int(status.get("id", row.get("gateway_client_id", 0))),
            key_prefix=str(row.get("key_prefix", "")),
            status=str(status.get("status", "")),
            can_call_api=bool(status.get("can_call_api", False)),
            limits=status.get("limits"),
            last_used_at=status.get("last_used_at"),
        )

    def rotate_key(self, subject: str, ip: str | None = None) -> AiKeyIssuedResponse:
        """Rotate the caller's active key, returning the new one (shown once)."""

        row = self._normalized(self._repository.get_ai_key(subject))
        old_api_key = str(row["api_key"])

        credential = self._gateway.rotate(old_api_key)
        self._repository.rotate_ai_key(
            subject,
            credential.client_id,
            credential.key_prefix,
            credential.api_key,
            ip,
        )
        logger.info(
            "AI Gateway key rotated",
            extra={"subject": subject, "key_prefix": credential.key_prefix},
        )
        return AiKeyIssuedResponse(
            client_id=credential.client_id,
            api_key=credential.api_key,
            key_prefix=credential.key_prefix,
            base_url=f"{self._gateway_base_url}/v1",
        )

    def revoke_key(self, subject: str, ip: str | None = None) -> None:
        """Revoke the caller's active key.

        The gateway has no true delete endpoint (per its own "Guía de
        consumo") -- rotating first invalidates the live key immediately
        (the gateway's own no-grace-period guarantee), then the freshly
        rotated key is discarded rather than stored, so nothing usable
        survives on either side.
        """

        row = self._normalized(self._repository.get_ai_key(subject))
        old_api_key = str(row["api_key"])
        self._gateway.rotate(old_api_key)  # invalidates the live key; result intentionally discarded
        self._repository.revoke_ai_key(subject, ip)
        logger.info("AI Gateway key revoked", extra={"subject": subject})

    def get_usage(self, subject: str, start: str | None, end: str | None) -> AiUsageResponse:
        """Return the caller's own consumption, proxied from the gateway."""

        row = self._normalized(self._repository.get_ai_key(subject))
        api_key = str(row["api_key"])
        usage = self._gateway.get_usage(api_key, start, end)
        return AiUsageResponse(**usage)

    @staticmethod
    def _normalized(row: Mapping[str, Any]) -> dict[str, Any]:
        return {str(key).lower(): value for key, value in row.items()}
