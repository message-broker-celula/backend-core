"""Contract for talking to the provisioner sidecar over HTTP.

Declares WHAT the provisioning domain needs from the sidecar -- create,
stop, start, remove a container -- without knowing HOW the transport works.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable


@dataclass(frozen=True, slots=True)
class ProvisionedContainer:
    """Result of successfully creating and starting an engine container."""

    container_name: str
    ready: bool


@runtime_checkable
class ProvisionerClientProtocol(Protocol):
    """Persistence-free contract for the provisioner sidecar's container API."""

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
        """Create, start, and wait for readiness of a new engine container.

        Raises:
            PortInUseError: When the sidecar/Docker reports the host port is
                already bound -- the caller should pick a new port and retry.
            ProvisioningTimeoutError: When the container never became ready.
            ProvisionerRequestError: For any other transport/sidecar failure.
        """
        ...

    def stop_container(self, name: str) -> None:
        """Stop (without removing) a running engine container."""
        ...

    def start_container(self, name: str) -> None:
        """Start a previously stopped engine container."""
        ...

    def remove_container(self, name: str) -> None:
        """Stop (if running), remove the container, and remove its volume."""
        ...
