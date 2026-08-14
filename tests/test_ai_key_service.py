import pytest

from app.ai.exceptions.ai_exceptions import AiGatewayAuthError
from app.ai.interfaces.ai_gateway_client import GatewayCredential
from app.ai.services.ai_key_service import AiKeyService
from app.repositories.exceptions.database_exceptions import BusinessRuleViolationError


class FakeGatewayClient:
    def __init__(self) -> None:
        self.register_calls: list[dict] = []
        self.rotate_calls: list[str] = []
        self.status_result: dict = {"id": 7, "can_call_api": True, "status": "approved", "limits": {}}
        self.usage_result: dict = {
            "start": "2026-08-01",
            "end": "2026-08-06",
            "total_requests": 5,
            "prompt_tokens": 10,
            "completion_tokens": 20,
            "total_tokens": 30,
        }
        self.status_raises: Exception | None = None

    def register(self, *, name, email, organization, intended_use):
        self.register_calls.append({"name": name, "email": email})
        return GatewayCredential(client_id=7, api_key="sk_live_new", key_prefix="sk_live_new1")

    def get_status(self, api_key):
        if self.status_raises:
            raise self.status_raises
        return self.status_result

    def rotate(self, api_key):
        self.rotate_calls.append(api_key)
        return GatewayCredential(client_id=7, api_key="sk_live_rotated", key_prefix="sk_live_rota")

    def get_usage(self, api_key, start=None, end=None):
        return self.usage_result


class FakeAiKeyRepository:
    def __init__(self) -> None:
        self.profile = {"nombre": "Usuario Uno", "correo": "uno@example.com"}
        self.active_key: dict | None = {
            "api_key": "sk_live_old",
            "key_prefix": "sk_live_old1",
            "gateway_client_id": 7,
        }
        self.registered: list[dict] = []
        self.rotated: list[dict] = []
        self.revoked_subject: str | None = None

    def get_user_profile(self, subject):
        return self.profile

    def register_ai_key(self, subject, gateway_client_id, key_prefix, api_key, ip=None):
        self.registered.append(
            {"subject": subject, "client_id": gateway_client_id, "prefix": key_prefix, "key": api_key}
        )
        return {"id_clave_ia": "clave-1"}

    def get_ai_key(self, subject):
        if self.active_key is None:
            raise BusinessRuleViolationError(procedure_name="sp_ObtenerClaveIA", detail="No tienes una clave de IA activa.")
        return self.active_key

    def rotate_ai_key(self, subject, gateway_client_id, key_prefix, api_key, ip=None):
        self.rotated.append(
            {"subject": subject, "client_id": gateway_client_id, "prefix": key_prefix, "key": api_key}
        )

    def revoke_ai_key(self, subject, ip=None):
        self.revoked_subject = subject


def _service(repository: FakeAiKeyRepository, gateway: FakeGatewayClient) -> AiKeyService:
    return AiKeyService(repository=repository, gateway=gateway, gateway_base_url="https://gateway.example.com")


def test_issue_key_uses_the_users_own_profile_not_client_input() -> None:
    repository = FakeAiKeyRepository()
    gateway = FakeGatewayClient()
    service = _service(repository, gateway)

    result = service.issue_key("user-1", organization="Org", intended_use="testing", ip=None)

    assert gateway.register_calls == [{"name": "Usuario Uno", "email": "uno@example.com"}]
    assert result.api_key == "sk_live_new"
    assert result.base_url == "https://gateway.example.com/v1"
    assert repository.registered[0]["key"] == "sk_live_new"


def test_get_status_maps_gateway_id_to_client_id_and_hides_raw_key() -> None:
    repository = FakeAiKeyRepository()
    gateway = FakeGatewayClient()
    service = _service(repository, gateway)

    result = service.get_status("user-1")

    assert result.client_id == 7
    assert result.key_prefix == "sk_live_old1"
    assert result.can_call_api is True
    assert not hasattr(result, "api_key")


def test_get_status_raises_business_rule_violation_when_gateway_rejects_stored_key() -> None:
    repository = FakeAiKeyRepository()
    gateway = FakeGatewayClient()
    gateway.status_raises = AiGatewayAuthError("revoked upstream")
    service = _service(repository, gateway)

    with pytest.raises(BusinessRuleViolationError):
        service.get_status("user-1")


def test_get_status_propagates_no_active_key_as_business_rule_violation() -> None:
    repository = FakeAiKeyRepository()
    repository.active_key = None
    gateway = FakeGatewayClient()
    service = _service(repository, gateway)

    with pytest.raises(BusinessRuleViolationError):
        service.get_status("user-1")


def test_rotate_key_uses_old_key_to_authenticate_and_persists_new_one() -> None:
    repository = FakeAiKeyRepository()
    gateway = FakeGatewayClient()
    service = _service(repository, gateway)

    result = service.rotate_key("user-1", ip="127.0.0.1")

    assert gateway.rotate_calls == ["sk_live_old"]
    assert result.api_key == "sk_live_rotated"
    assert repository.rotated[0]["key"] == "sk_live_rotated"


def test_revoke_key_rotates_upstream_then_marks_revoked_locally() -> None:
    repository = FakeAiKeyRepository()
    gateway = FakeGatewayClient()
    service = _service(repository, gateway)

    service.revoke_key("user-1", ip="127.0.0.1")

    assert gateway.rotate_calls == ["sk_live_old"]  # invalidates the live key
    assert repository.revoked_subject == "user-1"


def test_get_usage_proxies_the_gateways_own_shape() -> None:
    repository = FakeAiKeyRepository()
    gateway = FakeGatewayClient()
    service = _service(repository, gateway)

    result = service.get_usage("user-1", start="2026-08-01", end="2026-08-06")

    assert result.total_requests == 5
    assert result.total_tokens == 30
