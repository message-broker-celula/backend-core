"""Host port allocation for auto-provisioned database engine containers.

Two layers, in order of preference:
1. SQL Server is asked which ports are already assigned
   (`PortLookupProtocol.list_assigned_ports`) -- an optimization that reduces
   collision retries. This call is allowed to fail (e.g. the backing SQL
   function doesn't exist yet); a failure just disables the optimization for
   that attempt, it never blocks allocation.
2. Docker's own port-bind failure (surfaced by the sidecar as a 409, mapped
   to PortInUseError) is the real, race-proof collision detector -- the
   caller (DatabaseProvisioningService) retries with a new candidate on it.
"""

from __future__ import annotations

import logging
import random

from app.provisioning.interfaces.port_lookup import PortLookupProtocol
from app.repositories.exceptions.database_exceptions import DatabaseIntegrationError

logger = logging.getLogger(__name__)


class PortAllocator:
    """Picks candidate host ports within a configured range."""

    def __init__(
        self,
        port_repository: PortLookupProtocol,
        range_start: int,
        range_end: int,
    ) -> None:
        """Initialize the allocator with a port lookup source and inclusive range."""

        self._port_repository = port_repository
        self._range_start = range_start
        self._range_end = range_end

    def next_candidate(self, excluded: set[int]) -> int:
        """Return a free-looking port in range, excluding known-taken ports.

        Raises:
            PortAllocationExhaustedError-eligible condition: callers should
                treat an empty free set as exhausted (see
                DatabaseProvisioningService, which owns that exception type).
        """

        taken = set(excluded)
        try:
            taken |= set(self._port_repository.list_assigned_ports())
        except DatabaseIntegrationError as exc:
            logger.warning(
                "Port lookup unavailable; falling back to blind random allocation",
                exc_info=exc,
            )

        free = [
            port
            for port in range(self._range_start, self._range_end + 1)
            if port not in taken
        ]
        if not free:
            return -1
        return random.choice(free)
