"""Provisioner sidecar configuration.

Deliberately tiny and separate from the backend's own settings module: this
process must never share config (or a process) with anything that touches
SQL Server or handles OAuth input.
"""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Sidecar configuration, loaded from its own `.env.provisioner`."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    shared_secret: str = ""
    docker_network: str = "provisioned_net"
    host_bind_address: str = "0.0.0.0"
    # 30s was too tight against real production MySQL first-boot latency on
    # a modest VPS (confirmed: a real create hit this ceiling exactly and
    # failed with ProvisioningTimeoutError even though earlier successful
    # runs had already taken 30-50s end-to-end). 60s gives real headroom.
    readiness_timeout_seconds: int = 60
    readiness_poll_interval_seconds: float = 1.0
    # Hard ceiling on simultaneously running provisioned instances (any
    # engine combined), independent of each engine's own mem_limit in
    # engines.py. This VPS has ~3.7GB total RAM shared with the actual
    # production SQL Server (not a container this process manages) plus
    # backend-core-backend/provisioner/landing -- there is no safe way to
    # let provisioned containers grow unbounded. 6 is a conservative number
    # confirmed against real headroom measured in production (~1.2GB free
    # after accounting for everything else); revisit if the VPS is resized.
    max_concurrent_containers: int = 6


settings = Settings()
