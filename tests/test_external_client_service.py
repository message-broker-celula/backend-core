import pytest

from app.external_clients.exceptions.external_client_exceptions import InvalidApiKeyError
from app.external_clients.schemas.external_client_schemas import ExternalClientKeyResponse
from app.external_clients.services.external_client_service import ExternalClientService


class FakeExternalClientRepository:
    def __init__(self) -> None:
        self.registered: list[dict] = []
        self.rotated: list[str] = []
        self.revoked: list[str] = []
        self.valid_keys: dict[str, str] = {}

    def register_external_client(self, team_name, contact_email, ip=None):
        self.registered.append({"team_name": team_name, "contact_email": contact_email, "ip": ip})
        subject = "user-1"
        self.valid_keys["pgk_live_new"] = subject
        return {"id_usuario": subject, "api_key": "pgk_live_new", "key_prefix": "pgk_live_ne"}

    def validate_api_key(self, api_key):
        return self.valid_keys.get(api_key)

    def rotate_api_key(self, api_key, ip=None):
        self.rotated.append(api_key)
        subject = self.valid_keys.pop(api_key, "user-1")
        self.valid_keys["pgk_live_rotated"] = subject
        return {"id_usuario": subject, "api_key": "pgk_live_rotated", "key_prefix": "pgk_live_ro"}

    def revoke_api_key(self, api_key, ip=None):
        self.revoked.append(api_key)
        self.valid_keys.pop(api_key, None)


def test_register_returns_the_raw_key_once() -> None:
    repository = FakeExternalClientRepository()
    service = ExternalClientService(repository=repository)

    result = service.register("Idempotencia", "equipo@idempotencia.dev", "127.0.0.1")

    assert isinstance(result, ExternalClientKeyResponse)
    assert result.client_id == "user-1"
    assert result.api_key == "pgk_live_new"
    assert repository.registered == [
        {"team_name": "Idempotencia", "contact_email": "equipo@idempotencia.dev", "ip": "127.0.0.1"}
    ]


def test_authenticate_resolves_subject_for_a_valid_key() -> None:
    repository = FakeExternalClientRepository()
    service = ExternalClientService(repository=repository)
    service.register("Idempotencia", "equipo@idempotencia.dev", None)

    assert service.authenticate("pgk_live_new") == "user-1"


def test_authenticate_raises_for_an_unknown_key() -> None:
    repository = FakeExternalClientRepository()
    service = ExternalClientService(repository=repository)

    with pytest.raises(InvalidApiKeyError):
        service.authenticate("pgk_live_does_not_exist")


def test_rotate_invalidates_the_old_key_immediately() -> None:
    repository = FakeExternalClientRepository()
    service = ExternalClientService(repository=repository)
    service.register("Idempotencia", "equipo@idempotencia.dev", None)

    result = service.rotate("pgk_live_new", None)

    assert result.api_key == "pgk_live_rotated"
    with pytest.raises(InvalidApiKeyError):
        service.authenticate("pgk_live_new")
    assert service.authenticate("pgk_live_rotated") == "user-1"


def test_revoke_invalidates_the_key() -> None:
    repository = FakeExternalClientRepository()
    service = ExternalClientService(repository=repository)
    service.register("Idempotencia", "equipo@idempotencia.dev", None)

    service.revoke("pgk_live_new", None)

    with pytest.raises(InvalidApiKeyError):
        service.authenticate("pgk_live_new")
