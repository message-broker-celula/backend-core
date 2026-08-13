"""Thin wrapper around docker-py -- the only module in this repo that talks
to the Docker Engine API.

This process is the sole holder of `/var/run/docker.sock` access, isolated
from backend-core-backend (which handles untrusted OAuth/user input) by
design -- see app/provisioning/ on the backend side for why.
"""

from __future__ import annotations

import logging
import time

import docker
from docker.errors import APIError, NotFound
from docker.types import Mount

from app.engines import get_engine_spec

logger = logging.getLogger(__name__)


class PortInUseError(Exception):
    """Raised when Docker refuses to bind the requested host port."""


class UnsupportedEngineError(Exception):
    """Raised when the requested engine has no EngineSpec registered."""


class ContainerNotFoundError(Exception):
    """Raised when an operation targets a container that does not exist."""


def _volume_name_for(container_name: str) -> str:
    return f"dbdata_{container_name}"


class DockerProvisionerClient:
    """Creates, stops, starts, and removes real database engine containers."""

    def __init__(
        self,
        network: str,
        mem_limit: str,
        cpu_limit: float,
        host_bind_address: str,
        readiness_timeout_seconds: int,
        readiness_poll_interval_seconds: float,
    ) -> None:
        """Initialize the Docker client and ensure the target network exists."""

        self._client = docker.from_env()
        self._network = network
        self._mem_limit = mem_limit
        self._cpu_limit = cpu_limit
        self._host_bind_address = host_bind_address
        self._readiness_timeout_seconds = readiness_timeout_seconds
        self._readiness_poll_interval_seconds = readiness_poll_interval_seconds
        self._ensure_network()

    def _ensure_network(self) -> None:
        try:
            self._client.networks.get(self._network)
        except NotFound:
            logger.info("Creating provisioning network", extra={"network": self._network})
            self._client.networks.create(self._network, driver="bridge")

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
    ) -> bool:
        """Create, start, and wait for readiness of a new engine container.

        Returns:
            True once the engine responds to its readiness check, False if
            it never became ready within the configured timeout.

        Raises:
            UnsupportedEngineError: When `engine` has no registered EngineSpec.
            PortInUseError: When Docker refuses to bind `host_port`.
        """

        spec = get_engine_spec(engine)
        if spec is None:
            raise UnsupportedEngineError(engine)

        environment = spec.env_builder(database_name, username, password, root_password)

        try:
            container = self._client.containers.run(
                f"{spec.image}:{version}",
                name=name,
                detach=True,
                environment=environment,
                ports={f"{spec.internal_port}/tcp": (self._host_bind_address, host_port)},
                network=self._network,
                mem_limit=self._mem_limit,
                nano_cpus=int(self._cpu_limit * 1_000_000_000),
                mounts=[Mount(target="/var/lib/mysql", source=_volume_name_for(name), type="volume")],
                restart_policy={"Name": "unless-stopped"},
            )
        except APIError as exc:
            message = str(exc).lower()
            if "port is already allocated" in message or "address already in use" in message:
                raise PortInUseError(f"Host port {host_port} is already in use") from exc
            raise

        return self._wait_ready(container, spec.readiness_cmd)

    def _wait_ready(self, container, readiness_cmd: list[str]) -> bool:
        deadline = time.monotonic() + self._readiness_timeout_seconds
        while time.monotonic() < deadline:
            container.reload()
            if container.status == "running":
                try:
                    exit_code, _ = container.exec_run(readiness_cmd)
                    if exit_code == 0:
                        return True
                except APIError:
                    pass
            time.sleep(self._readiness_poll_interval_seconds)
        return False

    def stop_container(self, name: str) -> None:
        """Stop a running container without removing it."""

        self._get_container(name).stop()

    def start_container(self, name: str) -> None:
        """Start a previously stopped container."""

        self._get_container(name).start()

    def remove_container(self, name: str) -> None:
        """Stop (if running), remove the container, and remove its volume.

        Idempotent: removing an already-absent container is a no-op, so
        retries after a partial failure are safe.
        """

        try:
            container = self._client.containers.get(name)
        except NotFound:
            return
        container.remove(force=True)
        try:
            self._client.volumes.get(_volume_name_for(name)).remove()
        except NotFound:
            pass

    def _get_container(self, name: str):
        try:
            return self._client.containers.get(name)
        except NotFound as exc:
            raise ContainerNotFoundError(name) from exc
