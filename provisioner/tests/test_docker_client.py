from unittest.mock import MagicMock, patch

import pytest
from docker.errors import APIError, NotFound

from app.docker_client import (
    ContainerNotFoundError,
    DockerProvisionerClient,
    PortInUseError,
    UnsupportedEngineError,
)


def _fake_docker() -> MagicMock:
    fake = MagicMock()
    fake.networks.get.side_effect = NotFound("missing")
    return fake


def _make_client(fake_docker_client: MagicMock, **overrides: object) -> DockerProvisionerClient:
    kwargs = {
        "network": "test_net",
        "mem_limit": "128m",
        "cpu_limit": 0.25,
        "host_bind_address": "0.0.0.0",
        "readiness_timeout_seconds": 0.05,
        "readiness_poll_interval_seconds": 0.01,
        **overrides,
    }
    with patch("app.docker_client.docker.from_env", return_value=fake_docker_client):
        return DockerProvisionerClient(**kwargs)


def test_ensure_network_creates_missing_network() -> None:
    fake = _fake_docker()

    _make_client(fake)

    fake.networks.create.assert_called_once_with("test_net", driver="bridge")


def test_create_container_raises_unsupported_engine() -> None:
    client = _make_client(_fake_docker())

    with pytest.raises(UnsupportedEngineError):
        client.create_container(
            engine="postgres",
            version="16",
            name="dbinst-1",
            host_port=1,
            database_name="db",
            username="u",
            password="p",
            root_password="r",
        )


def test_create_container_maps_port_conflict_to_port_in_use_error() -> None:
    fake = _fake_docker()
    fake.containers.run.side_effect = APIError(
        "Bind for 0.0.0.0:30000 failed: port is already allocated"
    )
    client = _make_client(fake)

    with pytest.raises(PortInUseError):
        client.create_container(
            engine="mysql",
            version="8.4",
            name="dbinst-30000",
            host_port=30000,
            database_name="db",
            username="u",
            password="p",
            root_password="r",
        )


def test_create_container_waits_for_readiness_and_returns_true() -> None:
    fake = _fake_docker()
    fake_container = MagicMock()
    fake_container.status = "running"
    fake_container.exec_run.return_value = (0, b"")
    fake.containers.run.return_value = fake_container
    client = _make_client(fake)

    ready = client.create_container(
        engine="mysql",
        version="8.4",
        name="dbinst-30001",
        host_port=30001,
        database_name="db",
        username="u",
        password="p",
        root_password="r",
    )

    assert ready is True


def test_create_container_returns_false_when_never_ready() -> None:
    fake = _fake_docker()
    fake_container = MagicMock()
    fake_container.status = "starting"
    fake.containers.run.return_value = fake_container
    client = _make_client(fake)

    ready = client.create_container(
        engine="mysql",
        version="8.4",
        name="dbinst-30002",
        host_port=30002,
        database_name="db",
        username="u",
        password="p",
        root_password="r",
    )

    assert ready is False


def test_remove_container_is_idempotent_when_missing() -> None:
    fake = _fake_docker()
    fake.containers.get.side_effect = NotFound("missing")
    client = _make_client(fake)

    client.remove_container("dbinst-99999")  # must not raise


def test_stop_container_raises_when_missing() -> None:
    fake = _fake_docker()
    fake.containers.get.side_effect = NotFound("missing")
    client = _make_client(fake)

    with pytest.raises(ContainerNotFoundError):
        client.stop_container("dbinst-99999")
