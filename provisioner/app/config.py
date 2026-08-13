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
    # MySQL 8.4's default my.cnf (InnoDB buffer pool + performance_schema +
    # per-connection buffers) does not reliably start under ~300-400m --
    # 512m is a safe floor confirmed against a real OOMKilled=true crash
    # loop at 256m. Tune down per-engine later if a smaller footprint is
    # confirmed safe for the actual quota tiers offered.
    container_mem_limit: str = "512m"
    container_cpu_limit: float = 0.5
    host_bind_address: str = "0.0.0.0"
    readiness_timeout_seconds: int = 30
    readiness_poll_interval_seconds: float = 1.0


settings = Settings()
