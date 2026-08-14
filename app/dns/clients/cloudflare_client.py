"""Cloudflare API v4 client for user self-service DNS subdomains.

Only talks to Cloudflare's DNS record endpoints for a single, pre-configured
zone -- never touches zone settings, other zones, or account-level
resources. The API token is expected to be scoped (Zone.DNS edit on this
one zone) and IP-filtered to this backend's egress IP in the Cloudflare
dashboard.
"""

from __future__ import annotations

import logging

import httpx

from app.dns.exceptions.dns_exceptions import DnsProviderError, DnsRecordConflictError

logger = logging.getLogger(__name__)

_API_BASE = "https://api.cloudflare.com/client/v4"


class CloudflareDnsClient:
    """Concrete DnsClientProtocol implementation backed by the Cloudflare API."""

    def __init__(self, api_token: str, zone_id: str, timeout: int) -> None:
        """Initialize the client with the zone-scoped API token and target zone."""

        self._zone_id = zone_id
        self._timeout = timeout
        self._headers = {
            "Authorization": f"Bearer {api_token}",
            "Content-Type": "application/json",
        }

    def record_exists(self, fqdn: str) -> bool:
        """Return whether an A record already exists for the given FQDN.

        Also doubles as the "is this record active" check DnsProvisioningService
        uses -- every record this client creates has `proxied: True`, so public
        DNS resolution (even Cloudflare's own DNS-over-HTTPS resolver) never
        returns the origin IP for it, only Cloudflare's edge IPs. Comparing a
        resolved answer against the origin IP would therefore report "not
        propagated" forever. Cloudflare is authoritative for its own zone, so
        checking the record's existence via its API is both correct and
        effectively instant -- no propagation delay to account for.
        """

        return self._find_record_id(fqdn) is not None

    def create_record(self, fqdn: str, target_ip: str) -> str:
        """Create a proxied A record pointing at target_ip, return its id."""

        if self.record_exists(fqdn):
            raise DnsRecordConflictError(f"A DNS record already exists for '{fqdn}'")

        response = self._request(
            "POST",
            f"/zones/{self._zone_id}/dns_records",
            json={
                "type": "A",
                "name": fqdn,
                "content": target_ip,
                "ttl": 1,  # "automatic" -- required by Cloudflare when proxied
                "proxied": True,
            },
        )
        body = response.json()
        if not body.get("success"):
            raise DnsProviderError(f"Cloudflare rejected record creation for '{fqdn}': {body.get('errors')}")
        return str(body["result"]["id"])

    def delete_record(self, fqdn: str) -> None:
        """Delete the A record for the given FQDN, if any (idempotent)."""

        record_id = self._find_record_id(fqdn)
        if record_id is None:
            return
        self._request("DELETE", f"/zones/{self._zone_id}/dns_records/{record_id}")

    def _find_record_id(self, fqdn: str) -> str | None:
        response = self._request(
            "GET",
            f"/zones/{self._zone_id}/dns_records",
            params={"type": "A", "name": fqdn},
        )
        body = response.json()
        if not body.get("success"):
            raise DnsProviderError(f"Cloudflare rejected record lookup for '{fqdn}': {body.get('errors')}")
        results = body.get("result", [])
        return str(results[0]["id"]) if results else None

    def _request(self, method: str, path: str, **kwargs: object) -> httpx.Response:
        try:
            response = httpx.request(
                method,
                f"{_API_BASE}{path}",
                headers=self._headers,
                timeout=self._timeout,
                **kwargs,
            )
        except httpx.HTTPError as exc:
            logger.error("Cloudflare request failed", extra={"path": path}, exc_info=exc)
            raise DnsProviderError(f"Could not reach Cloudflare at {path}") from exc

        if response.status_code >= 500:
            raise DnsProviderError(f"Cloudflare failed on {path}: {response.status_code} {response.text}")
        if response.status_code == 401 or response.status_code == 403:
            # Deliberately no response body in the log/exception message --
            # Cloudflare's 403 body can echo back client IP/token metadata,
            # and this is the one failure mode most likely to be a
            # misconfigured token, not something a caller can fix.
            raise DnsProviderError(f"Cloudflare authentication/authorization failed on {path} ({response.status_code})")
        return response
