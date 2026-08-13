"""HTTP client for the provisioner sidecar.

The sidecar is the only process with Docker socket access; this backend only
ever talks to it over plain HTTP on the internal docker network, gated by a
shared-secret header (internal-network-only, no OAuth/JWT needed here).
"""

from __future__ import annotations

import logging

import httpx

from app.provisioning.exceptions.provisioning_exceptions import (
    PortInUseError,
    ProvisionerRequestError,
    ProvisioningTimeoutError,
)
from app.provisioning.interfaces.provisioner_client import ProvisionedContainer

logger = logging.getLogger(__name__)

_TOKEN_HEADER = "X-Internal-Token"


class HttpProvisionerClient:
    """Concrete ProvisionerClientProtocol implementation backed by httpx."""

    def __init__(self, base_url: str, shared_secret: str, timeout: int) -> None:
        """Initialize the client with the sidecar's base URL and shared secret."""

        self._base_url = base_url.rstrip("/")
        self._headers = {_TOKEN_HEADER: shared_secret}
        self._timeout = timeout

    def create_container(
        self,
        *,
        engine: str,
        version: str,
        name: str,
        host_port: int,
        database_name: str,
        username: str,
        password: str,
        root_password: str,
    ) -> ProvisionedContainer:
        """Ask the sidecar to create, start, and wait for readiness of a container."""

        payload = {
            "engine": engine,
            "version": version,
            "name": name,
            "host_port": host_port,
            "database_name": database_name,
            "username": username,
            "password": password,
            "root_password": root_password,
        }
        response = self._request("POST", "/containers", json=payload)
        if response.status_code == 409:
            raise PortInUseError(f"Host port {host_port} is already in use")
        if response.status_code >= 400:
            raise ProvisionerRequestError(
                f"Provisioner rejected container creation: {response.status_code} {response.text}"
            )

        data = response.json()
        if not data.get("ready", False):
            raise ProvisioningTimeoutError(f"Container '{name}' did not become ready in time")
        return ProvisionedContainer(container_name=name, ready=True)

    def stop_container(self, name: str) -> None:
        """Stop a running engine container without removing it."""

        self._request("POST", f"/containers/{name}/stop")

    def start_container(self, name: str) -> None:
        """Start a previously stopped engine container."""

        self._request("POST", f"/containers/{name}/start")

    def remove_container(self, name: str) -> None:
        """Stop (if running), remove the container, and remove its volume."""

        self._request("DELETE", f"/containers/{name}")

    def _request(self, method: str, path: str, **kwargs: object) -> httpx.Response:
        try:
            response = httpx.request(
                method,
                f"{self._base_url}{path}",
                headers=self._headers,
                timeout=self._timeout,
                **kwargs,
            )
        except httpx.HTTPError as exc:
            logger.error("Provisioner request failed", extra={"path": path}, exc_info=exc)
            raise ProvisionerRequestError(f"Could not reach provisioner at {path}") from exc

        if path.startswith("/containers") and response.status_code == 404:
            raise ProvisionerRequestError(f"Provisioner has no container for {path}")
        if response.status_code >= 500:
            raise ProvisionerRequestError(
                f"Provisioner failed on {path}: {response.status_code} {response.text}"
            )
        return response
