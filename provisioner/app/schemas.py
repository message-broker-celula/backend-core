"""Request/response models for the provisioner's internal HTTP API."""

from __future__ import annotations

from pydantic import BaseModel


class CreateContainerRequest(BaseModel):
    """Body for POST /containers."""

    engine: str
    version: str
    name: str
    host_port: int
    database_name: str
    username: str
    password: str
    root_password: str


class CreateContainerResponse(BaseModel):
    """Response for POST /containers."""

    container_id: str
    ready: bool


class StatusResponse(BaseModel):
    """Generic acknowledgement for stop/start/remove operations."""

    status: str
