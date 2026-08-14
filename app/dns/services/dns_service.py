"""User self-service DNS subdomain orchestration.

Coordinates name validation and the Cloudflare record lifecycle into a
`provision()`/`deprovision()`/`check_status()` surface for
CelulaOrchestrationService to use -- SQL Server stays the source of truth
for ownership/quotas; this module only makes the real DNS record exist.
"""

from __future__ import annotations

import logging
import re

from app.dns.interfaces.dns_client import DnsClientProtocol
from app.repositories.exceptions.database_exceptions import BusinessRuleViolationError

logger = logging.getLogger(__name__)

# Standard DNS label: lowercase alphanumeric, hyphens allowed but not at the
# start/end, max 63 chars (the actual DNS protocol limit per label).
_DNS_LABEL_PATTERN = re.compile(r"^[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?$")


def is_valid_dns_label(name: str) -> bool:
    """Return whether `name` is a valid single DNS label."""

    return bool(_DNS_LABEL_PATTERN.match(name))


class DnsProvisioningService:
    """Orchestrates real Cloudflare DNS record provisioning for célula services."""

    def __init__(self, client: DnsClientProtocol, root_domain: str, target_ip: str) -> None:
        """Initialize the service with its Cloudflare client and target configuration."""

        self._client = client
        self._root_domain = root_domain
        self._target_ip = target_ip

    def build_fqdn(self, service_name: str, celula_name: str) -> str:
        """Return the fully-qualified domain name for a service under a célula."""

        return f"{service_name}.{celula_name}.{self._root_domain}"

    def provision(self, service_name: str, celula_name: str) -> str:
        """Create the real DNS record for a new célula service, return its FQDN.

        Raises:
            BusinessRuleViolationError: When `service_name` is not a valid
                DNS label (a caller-facing 400, not a service outage).
            DnsRecordConflictError / DnsProviderError: For Cloudflare
                failures (mapped to 503 by the existing route handling).
        """

        if not is_valid_dns_label(service_name):
            raise BusinessRuleViolationError(
                procedure_name="dns_provisioning",
                detail=f"'{service_name}' is not a valid subdomain name",
            )

        fqdn = self.build_fqdn(service_name, celula_name)
        self._client.create_record(fqdn, self._target_ip)
        logger.info("DNS record created", extra={"fqdn": fqdn})
        return fqdn

    def deprovision(self, service_name: str, celula_name: str) -> None:
        """Remove the real DNS record backing a célula service."""

        fqdn = self.build_fqdn(service_name, celula_name)
        self._client.delete_record(fqdn)
        logger.info("DNS record removed", extra={"fqdn": fqdn})

    def check_status(self, service_name: str, celula_name: str) -> dict[str, bool | str]:
        """Return propagation status for a célula service's DNS record.

        "Propagated" means the record exists in Cloudflare (authoritative,
        effectively instant), not that it resolves to the origin IP from the
        public internet -- every record here is proxied, so public resolvers
        only ever return Cloudflare's edge IPs, never the origin.
        """

        fqdn = self.build_fqdn(service_name, celula_name)
        propagated = self._client.record_exists(fqdn)
        return {"fqdn": fqdn, "propagated": propagated}
