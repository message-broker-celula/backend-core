"""Database engine provisioning orchestration.

Coordinates port allocation, credential generation, and the provisioner
sidecar call into a single `provision()`/`deprovision()`/`stop()`/`start()`
surface for DatabaseService to use -- SQL Server stays the only place
business rules (quotas, TTL, ownership) are enforced; this module only
makes a real container exist.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from app.provisioning.credentials import (
    generate_password,
    generate_username,
    sanitize_database_name,
)
from app.provisioning.exceptions.provisioning_exceptions import (
    PortAllocationExhaustedError,
    PortInUseError,
)
from app.provisioning.interfaces.provisioner_client import ProvisionerClientProtocol
from app.provisioning.naming import container_name_for_port
from app.provisioning.port_allocator import PortAllocator
from app.repositories.exceptions.database_exceptions import BusinessRuleViolationError

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class ProvisionedDatabase:
    """Real, ready-to-use connection details for a freshly provisioned engine."""

    host: str
    port: int
    username: str
    password: str
    database_name: str
    container_name: str


class DatabaseProvisioningService:
    """Orchestrates real engine container provisioning for `/databases`."""

    def __init__(
        self,
        client: ProvisionerClientProtocol,
        port_allocator: PortAllocator,
        public_host: str,
        supported_engines: list[str],
        password_length: int,
        port_allocation_attempts: int,
    ) -> None:
        """Initialize the service with its collaborators and configuration."""

        self._client = client
        self._port_allocator = port_allocator
        self._public_host = public_host
        self._supported_engines = set(supported_engines)
        self._password_length = password_length
        self._port_allocation_attempts = port_allocation_attempts

    def provision(self, *, engine: str, version: str, requested_name: str) -> ProvisionedDatabase:
        """Provision a new, ready engine container and return real connection details.

        Raises:
            BusinessRuleViolationError: When the engine isn't supported (a
                caller-facing 400, not a service outage).
            PortAllocationExhaustedError: When no port could be bound after
                the configured retry budget.
            ProvisioningError subclasses: For sidecar/transport failures.
        """

        if engine not in self._supported_engines:
            raise BusinessRuleViolationError(
                procedure_name="provisioning",
                detail=f"Engine '{engine}' is not supported",
            )

        database_name = sanitize_database_name(requested_name)
        username = generate_username()
        password = generate_password(self._password_length)
        root_password = generate_password(self._password_length)

        excluded: set[int] = set()
        last_error: PortInUseError | None = None
        for _ in range(self._port_allocation_attempts):
            port = self._port_allocator.next_candidate(excluded)
            if port == -1:
                break
            excluded.add(port)
            name = container_name_for_port(port)
            try:
                self._client.create_container(
                    engine=engine.lower(),
                    version=version,
                    name=name,
                    host_port=port,
                    database_name=database_name,
                    username=username,
                    password=password,
                    root_password=root_password,
                )
            except PortInUseError as exc:
                logger.warning("Port %s already in use, retrying allocation", port)
                last_error = exc
                continue

            return ProvisionedDatabase(
                host=self._public_host,
                port=port,
                username=username,
                password=password,
                database_name=database_name,
                container_name=name,
            )

        raise PortAllocationExhaustedError(
            "Could not allocate a free host port for provisioning"
        ) from last_error

    def deprovision(self, *, port: int) -> None:
        """Stop, remove, and free the container backing a database instance."""

        self._client.remove_container(container_name_for_port(port))

    def stop(self, *, port: int) -> None:
        """Stop (without removing) the container backing a database instance."""

        self._client.stop_container(container_name_for_port(port))

    def start(self, *, port: int) -> None:
        """Start the previously stopped container backing a database instance."""

        self._client.start_container(container_name_for_port(port))
