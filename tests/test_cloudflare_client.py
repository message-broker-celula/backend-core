from unittest.mock import MagicMock, patch

import httpx
import pytest

from app.dns.clients.cloudflare_client import CloudflareDnsClient
from app.dns.exceptions.dns_exceptions import DnsProviderError, DnsRecordConflictError


def _client() -> CloudflareDnsClient:
    return CloudflareDnsClient(api_token="test-token", zone_id="zone-123", timeout=5)


def _response(status_code: int, json_body: dict) -> MagicMock:
    response = MagicMock(spec=httpx.Response)
    response.status_code = status_code
    response.json.return_value = json_body
    response.text = str(json_body)
    return response


def test_record_exists_true_when_cloudflare_returns_a_match() -> None:
    client = _client()
    list_response = _response(200, {"success": True, "result": [{"id": "rec-1"}]})

    with patch("app.dns.clients.cloudflare_client.httpx.request", return_value=list_response) as mock_request:
        assert client.record_exists("api.alpha.coderhivex.com") is True

    mock_request.assert_called_once()
    assert mock_request.call_args.kwargs["params"] == {"type": "A", "name": "api.alpha.coderhivex.com"}


def test_record_exists_false_when_cloudflare_returns_no_matches() -> None:
    client = _client()
    list_response = _response(200, {"success": True, "result": []})

    with patch("app.dns.clients.cloudflare_client.httpx.request", return_value=list_response):
        assert client.record_exists("api.alpha.coderhivex.com") is False


def test_create_record_raises_conflict_when_record_already_exists() -> None:
    client = _client()
    list_response = _response(200, {"success": True, "result": [{"id": "rec-1"}]})

    with patch("app.dns.clients.cloudflare_client.httpx.request", return_value=list_response):
        with pytest.raises(DnsRecordConflictError):
            client.create_record("api.alpha.coderhivex.com", "46.224.97.85")


def test_create_record_sends_proxied_a_record_and_returns_id() -> None:
    client = _client()
    empty_list_response = _response(200, {"success": True, "result": []})
    create_response = _response(200, {"success": True, "result": {"id": "rec-new"}})

    with patch(
        "app.dns.clients.cloudflare_client.httpx.request",
        side_effect=[empty_list_response, create_response],
    ) as mock_request:
        record_id = client.create_record("api.alpha.coderhivex.com", "46.224.97.85")

    assert record_id == "rec-new"
    create_call = mock_request.call_args_list[1]
    assert create_call.kwargs["json"] == {
        "type": "A",
        "name": "api.alpha.coderhivex.com",
        "content": "46.224.97.85",
        "ttl": 1,
        "proxied": True,
    }


def test_delete_record_is_idempotent_when_record_does_not_exist() -> None:
    client = _client()
    empty_list_response = _response(200, {"success": True, "result": []})

    with patch("app.dns.clients.cloudflare_client.httpx.request", return_value=empty_list_response) as mock_request:
        client.delete_record("api.alpha.coderhivex.com")  # must not raise

    mock_request.assert_called_once()  # only the lookup, no DELETE call


def test_delete_record_deletes_the_matched_record() -> None:
    client = _client()
    list_response = _response(200, {"success": True, "result": [{"id": "rec-1"}]})
    delete_response = _response(200, {"success": True})

    with patch(
        "app.dns.clients.cloudflare_client.httpx.request",
        side_effect=[list_response, delete_response],
    ) as mock_request:
        client.delete_record("api.alpha.coderhivex.com")

    delete_call = mock_request.call_args_list[1]
    assert delete_call.args[0] == "DELETE"
    assert delete_call.args[1].endswith("/zones/zone-123/dns_records/rec-1")


def test_request_raises_provider_error_on_auth_failure_without_leaking_body() -> None:
    client = _client()
    auth_failure = _response(403, {"success": False, "errors": [{"code": 9109, "message": "leaked-detail"}]})

    with patch("app.dns.clients.cloudflare_client.httpx.request", return_value=auth_failure):
        with pytest.raises(DnsProviderError) as exc_info:
            client.record_exists("api.alpha.coderhivex.com")

    assert "leaked-detail" not in str(exc_info.value)


def test_request_raises_provider_error_on_transport_failure() -> None:
    client = _client()

    with patch("app.dns.clients.cloudflare_client.httpx.request", side_effect=httpx.ConnectError("boom")):
        with pytest.raises(DnsProviderError):
            client.record_exists("api.alpha.coderhivex.com")
