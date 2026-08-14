"""Supported database engine registry.

The single extensibility point for adding new engines -- add a dict entry
here, nothing in docker_client.py or main.py needs to change.

Resource limits are per-engine (not a single global setting) because engines
have very different baseline footprints. The VPS this runs on has ~3.7GB
total RAM shared with the actual production SQL Server, so every engine here
is deliberately tuned down from its image defaults -- both the container
`mem_limit` (the hard cap Docker enforces) and the engine's own startup
flags (so it does not try to use memory it will never get, which is what
causes OOMKilled crash loops instead of a clean failure).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class EngineSpec:
    """Everything docker_client needs to run one kind of database engine."""

    image: str
    internal_port: int
    env_builder: Callable[[str, str, str, str], dict[str, str]]
    readiness_cmd: list[str]
    data_dir: str
    mem_limit: str
    cpu_limit: float
    command: list[str] | None = field(default=None)


def _build_mysql_env(database_name: str, username: str, password: str, root_password: str) -> dict[str, str]:
    return {
        "MYSQL_ROOT_PASSWORD": root_password,
        "MYSQL_DATABASE": database_name,
        "MYSQL_USER": username,
        "MYSQL_PASSWORD": password,
    }


def _build_postgres_env(database_name: str, username: str, password: str, root_password: str) -> dict[str, str]:
    # Postgres has no separate "root" account distinct from the configured
    # superuser -- POSTGRES_USER *is* the superuser, so root_password is
    # unused here. Kept in the signature only so every engine matches the
    # same Callable shape docker_client expects.
    del root_password
    return {
        "POSTGRES_USER": username,
        "POSTGRES_PASSWORD": password,
        "POSTGRES_DB": database_name,
    }


ENGINE_REGISTRY: dict[str, EngineSpec] = {
    "mysql": EngineSpec(
        image="mysql",
        internal_port=3306,
        env_builder=_build_mysql_env,
        readiness_cmd=["mysqladmin", "ping", "--silent", "-h", "127.0.0.1"],
        data_dir="/var/lib/mysql",
        # 512m was the safe floor confirmed against a real OOMKilled=true
        # crash loop at 256m -- but that was with MySQL's *default* my.cnf,
        # which reserves a large InnoDB buffer pool, performance_schema, and
        # generous per-connection buffers it will never need for a small
        # provisioned instance. Trimming those via `command` below lets the
        # actual footprint sit well under 512m, so the cap can come down too.
        mem_limit="320m",
        cpu_limit=0.4,
        command=[
            "--innodb-buffer-pool-size=64M",
            "--innodb-log-buffer-size=8M",
            "--key-buffer-size=8M",
            "--max-connections=30",
            "--table-open-cache=64",
            "--performance-schema=OFF",
        ],
    ),
    "postgres": EngineSpec(
        image="postgres",
        internal_port=5432,
        env_builder=_build_postgres_env,
        readiness_cmd=["pg_isready", "-h", "127.0.0.1"],
        data_dir="/var/lib/postgresql/data",
        # Postgres's own defaults are already much lighter than MySQL's
        # (128MB shared_buffers, no equivalent of performance_schema on by
        # default), so this cap can be conservative from the start rather
        # than needing the same "found OOM in prod, raise it" cycle MySQL
        # went through.
        mem_limit="192m",
        cpu_limit=0.3,
        command=[
            "-c",
            "shared_buffers=32MB",
            "-c",
            "max_connections=20",
            "-c",
            "work_mem=4MB",
            "-c",
            "maintenance_work_mem=32MB",
        ],
    ),
}


def get_engine_spec(engine: str) -> EngineSpec | None:
    """Return the EngineSpec for a supported engine name, case-insensitive."""

    return ENGINE_REGISTRY.get(engine.lower())
