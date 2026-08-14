"""Contract for talking to the DNS provider (Cloudflare) over HTTP.

Declares WHAT the DNS domain needs from the provider -- create/check/delete
a record -- without knowing HOW the transport works, mirroring
app.provisioning.interfaces.provisioner_client.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class DnsClientProtocol(Protocol):
    """Persistence-free contract for the DNS provider's record API."""

    def record_exists(self, fqdn: str) -> bool:
        """Return whether an A record already exists for the given FQDN."""
        ...

    def create_record(self, fqdn: str, target_ip: str) -> str:
        """Create a proxied A record pointing at target_ip, return its id.

        Raises:
            DnsRecordConflictError: When a record for this FQDN already exists.
            DnsProviderError: For any other provider/transport failure.
        """
        ...

    def delete_record(self, fqdn: str) -> None:
        """Delete the A record for the given FQDN, if any (idempotent)."""
        ...

    def resolves_to(self, fqdn: str, expected_ip: str) -> bool:
        """Return whether fqdn currently resolves to expected_ip (propagation check)."""
        ...
