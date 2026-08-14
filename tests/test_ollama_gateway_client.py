from unittest.mock import MagicMock, patch

import httpx
import pytest

from app.ai.clients.ollama_gateway_client import OllamaGatewayClient
from app.ai.exceptions.ai_exceptions import AiGatewayAuthError, AiGatewayError


def _client() -> OllamaGatewayClient:
    return OllamaGatewayClient(base_url="https://gateway.example.com", timeout=5)


def _response(status_code: int, json_body: dict) -> MagicMock:
    response = MagicMock(spec=httpx.Response)
    response.status_code = status_code
    response.json.return_value = json_body
    response.text = str(json_body)
    return response


def test_register_sends_expected_payload_and_maps_response() -> None:
    client = _client()
    register_response = _response(
        201, {"client_id": 7, "api_key": "sk_live_abc", "key_prefix": "sk_live_abc1"}
    )

    with patch("app.ai.clients.ollama_gateway_client.httpx.request", return_value=register_response) as mock_request:
        credential = client.register(
            name="Usuario Uno", email="uno@example.com", organization=None, intended_use="test"
        )

    assert credential.client_id == 7
    assert credential.api_key == "sk_live_abc"
    assert credential.key_prefix == "sk_live_abc1"
    call = mock_request.call_args
    assert call.args[0] == "POST"
    assert call.args[1].endswith("/public/clients/register")
    assert call.kwargs["json"] == {
        "name": "Usuario Uno",
        "contact_email": "uno@example.com",
        "organization": None,
        "intended_use": "test",
    }
    assert "Authorization" not in call.kwargs["headers"]


def test_get_status_sends_bearer_auth_header() -> None:
    client = _client()
    status_response = _response(200, {"id": 7, "can_call_api": True, "status": "approved"})

    with patch("app.ai.clients.ollama_gateway_client.httpx.request", return_value=status_response) as mock_request:
        body = client.get_status("sk_live_abc")

    assert body["can_call_api"] is True
    assert mock_request.call_args.kwargs["headers"] == {"Authorization": "Bearer sk_live_abc"}


def test_rotate_maps_new_credential() -> None:
    client = _client()
    rotate_response = _response(
        200, {"client_id": 7, "api_key": "sk_live_new", "key_prefix": "sk_live_new1"}
    )

    with patch("app.ai.clients.ollama_gateway_client.httpx.request", return_value=rotate_response):
        credential = client.rotate("sk_live_old")

    assert credential.api_key == "sk_live_new"
    assert credential.key_prefix == "sk_live_new1"


def test_get_usage_forwards_start_and_end_params() -> None:
    client = _client()
    usage_response = _response(200, {"start": "2026-08-01", "end": "2026-08-06", "total_requests": 5})

    with patch("app.ai.clients.ollama_gateway_client.httpx.request", return_value=usage_response) as mock_request:
        client.get_usage("sk_live_abc", start="2026-08-01", end="2026-08-06")

    assert mock_request.call_args.kwargs["params"] == {"start": "2026-08-01", "end": "2026-08-06"}


def test_request_raises_auth_error_on_401() -> None:
    client = _client()
    unauthorized = _response(401, {"error": {"code": "invalid_request_error"}})

    with patch("app.ai.clients.ollama_gateway_client.httpx.request", return_value=unauthorized):
        with pytest.raises(AiGatewayAuthError):
            client.get_status("sk_live_revoked")


def test_request_raises_gateway_error_on_transport_failure() -> None:
    client = _client()

    with patch("app.ai.clients.ollama_gateway_client.httpx.request", side_effect=httpx.ConnectError("boom")):
        with pytest.raises(AiGatewayError):
            client.get_status("sk_live_abc")


def test_request_raises_gateway_error_on_server_failure() -> None:
    client = _client()
    server_error = _response(502, {"error": {"code": "api_error"}})

    with patch("app.ai.clients.ollama_gateway_client.httpx.request", return_value=server_error):
        with pytest.raises(AiGatewayError):
            client.get_status("sk_live_abc")
