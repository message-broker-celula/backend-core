"""Supported database engine registry.

The single extensibility point for adding new engines later (e.g. Postgres)
without touching docker_client.py or main.py -- add a dict entry here.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class EngineSpec:
    """Everything docker_client needs to run one kind of database engine."""

    image: str
    internal_port: int
    env_builder: Callable[[str, str, str, str], dict[str, str]]
    readiness_cmd: list[str]


def _build_mysql_env(database_name: str, username: str, password: str, root_password: str) -> dict[str, str]:
    return {
        "MYSQL_ROOT_PASSWORD": root_password,
        "MYSQL_DATABASE": database_name,
        "MYSQL_USER": username,
        "MYSQL_PASSWORD": password,
    }


ENGINE_REGISTRY: dict[str, EngineSpec] = {
    "mysql": EngineSpec(
        image="mysql",
        internal_port=3306,
        env_builder=_build_mysql_env,
        readiness_cmd=["mysqladmin", "ping", "--silent", "-h", "127.0.0.1"],
    ),
    # "postgres": EngineSpec(image="postgres", internal_port=5432, ...) -- future, not implemented in v1
}


def get_engine_spec(engine: str) -> EngineSpec | None:
    """Return the EngineSpec for a supported engine name, case-insensitive."""

    return ENGINE_REGISTRY.get(engine.lower())
