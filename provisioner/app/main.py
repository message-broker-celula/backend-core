"""Provisioner sidecar HTTP API.

The only process in this deployment with `/var/run/docker.sock` access.
backend-core-backend calls this over the internal docker network to
create/stop/start/remove real database engine containers -- it never touches
Docker directly, so a bug in the OAuth/user-input-handling backend can't
translate into control over the Docker host.

Auth is a single shared-secret header, sufficient for an internal-network-
only service -- no OAuth/JWT involved here.
"""

from __future__ import annotations

import logging
import secrets
from typing import Annotated

from fastapi import Depends, FastAPI, Header, HTTPException, status

from app.config import settings
from app.docker_client import (
    CapacityExceededError,
    ContainerNotFoundError,
    DockerProvisionerClient,
    PortInUseError,
    UnsupportedEngineError,
)
from app.schemas import CreateContainerRequest, CreateContainerResponse, StatusResponse

logger = logging.getLogger(__name__)

app = FastAPI(
    title="backend-core-provisioner",
    description="Internal sidecar; the only process with Docker socket access.",
)

_client: DockerProvisionerClient | None = None


def get_client() -> DockerProvisionerClient:
    """Lazily construct the Docker client so /health works even if the Docker daemon is briefly unavailable."""

    global _client
    if _client is None:
        _client = DockerProvisionerClient(
            network=settings.docker_network,
            host_bind_address=settings.host_bind_address,
            readiness_timeout_seconds=settings.readiness_timeout_seconds,
            readiness_poll_interval_seconds=settings.readiness_poll_interval_seconds,
            max_concurrent_containers=settings.max_concurrent_containers,
        )
    return _client


def verify_token(x_internal_token: str = Header(...)) -> None:
    """Reject requests without the shared secret configured for this deployment."""

    if not settings.shared_secret or not secrets.compare_digest(x_internal_token, settings.shared_secret):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid internal token")


@app.get("/health")
def health() -> dict[str, str]:
    """Unauthenticated liveness check, used by the compose healthcheck."""

    return {"status": "healthy"}


Client = Annotated[DockerProvisionerClient, Depends(get_client)]


@app.post(
    "/containers",
    response_model=CreateContainerResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(verify_token)],
)
def create_container(payload: CreateContainerRequest, client: Client) -> CreateContainerResponse:
    """Create, start, and wait for readiness of a new engine container."""

    try:
        ready = client.create_container(
            engine=payload.engine,
            version=payload.version,
            name=payload.name,
            host_port=payload.host_port,
            database_name=payload.database_name,
            username=payload.username,
            password=payload.password,
            root_password=payload.root_password,
        )
    except PortInUseError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="port_in_use") from exc
    except UnsupportedEngineError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=f"Unsupported engine '{exc}'"
        ) from exc
    except CapacityExceededError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc

    return CreateContainerResponse(container_id=payload.name, ready=ready)


@app.post(
    "/containers/{name}/stop",
    response_model=StatusResponse,
    dependencies=[Depends(verify_token)],
)
def stop_container(name: str, client: Client) -> StatusResponse:
    """Stop a running container without removing it."""

    try:
        client.stop_container(name)
    except ContainerNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="container_not_found") from exc
    return StatusResponse(status="stopped")


@app.post(
    "/containers/{name}/start",
    response_model=StatusResponse,
    dependencies=[Depends(verify_token)],
)
def start_container(name: str, client: Client) -> StatusResponse:
    """Start a previously stopped container."""

    try:
        client.start_container(name)
    except ContainerNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="container_not_found") from exc
    return StatusResponse(status="started")


@app.delete(
    "/containers/{name}",
    response_model=StatusResponse,
    dependencies=[Depends(verify_token)],
)
def remove_container(name: str, client: Client) -> StatusResponse:
    """Stop (if running), remove the container, and remove its volume."""

    client.remove_container(name)
    return StatusResponse(status="removed")
