"""HTTP client for the Ollama Gateway (a separate team's already-built,
OpenAI-compatible AI service -- see the gateway's own "Guía de consumo").

This backend only ever calls the gateway's `/public/*` client-management
endpoints (register/status/rotate/usage) to orchestrate key issuance on the
platform's behalf -- it never proxies `/v1/*` inference calls; end users'
own applications talk to those directly with the SDK.
"""

from __future__ import annotations

import logging

import httpx

from app.ai.exceptions.ai_exceptions import AiGatewayAuthError, AiGatewayError
from app.ai.interfaces.ai_gateway_client import GatewayCredential

logger = logging.getLogger(__name__)


class OllamaGatewayClient:
    """Concrete AiGatewayClientProtocol implementation backed by httpx."""

    def __init__(self, base_url: str, timeout: int) -> None:
        """Initialize the client with the gateway's base URL."""

        self._base_url = base_url.rstrip("/")
        self._timeout = timeout

    def register(
        self, *, name: str, email: str, organization: str | None, intended_use: str | None
    ) -> GatewayCredential:
        """Register a new gateway client, returning its immediately-usable key."""

        payload = {
            "name": name,
            "contact_email": email,
            "organization": organization,
            "intended_use": intended_use,
        }
        response = self._request("POST", "/public/clients/register", json=payload)
        body = response.json()
        return GatewayCredential(
            client_id=int(body["client_id"]),
            api_key=str(body["api_key"]),
            key_prefix=str(body["key_prefix"]),
        )

    def get_status(self, api_key: str) -> dict:
        """Return the gateway's own /public/clients/me payload for this key."""

        response = self._request("GET", "/public/clients/me", auth_key=api_key)
        return response.json()

    def rotate(self, api_key: str) -> GatewayCredential:
        """Rotate the given key, returning the new one."""

        response = self._request("POST", "/public/clients/me/rotate-key", auth_key=api_key)
        body = response.json()
        return GatewayCredential(
            client_id=int(body["client_id"]),
            api_key=str(body["api_key"]),
            key_prefix=str(body["key_prefix"]),
        )

    def get_usage(self, api_key: str, start: str | None = None, end: str | None = None) -> dict:
        """Return the gateway's own /public/clients/me/usage payload for this key."""

        params = {k: v for k, v in {"start": start, "end": end}.items() if v is not None}
        response = self._request("GET", "/public/clients/me/usage", auth_key=api_key, params=params)
        return response.json()

    def _request(
        self,
        method: str,
        path: str,
        *,
        auth_key: str | None = None,
        **kwargs: object,
    ) -> httpx.Response:
        headers = {"Authorization": f"Bearer {auth_key}"} if auth_key else {}
        try:
            response = httpx.request(
                method,
                f"{self._base_url}{path}",
                headers=headers,
                timeout=self._timeout,
                **kwargs,
            )
        except httpx.HTTPError as exc:
            logger.error("Ollama Gateway request failed", extra={"path": path}, exc_info=exc)
            raise AiGatewayError(f"Could not reach the AI gateway at {path}") from exc

        if response.status_code == 401:
            # A stored key the gateway no longer honors (revoked/expired
            # upstream, outside this platform's control) -- distinct from a
            # generic failure so the service layer can react (e.g. mark the
            # local record stale) instead of just surfacing a 503.
            raise AiGatewayAuthError(f"AI gateway rejected the stored API key on {path}")
        if response.status_code >= 500:
            raise AiGatewayError(f"AI gateway failed on {path}: {response.status_code} {response.text}")
        if response.status_code >= 400:
            raise AiGatewayError(f"AI gateway rejected the request on {path}: {response.status_code} {response.text}")
        return response
