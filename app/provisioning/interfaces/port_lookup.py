"""Port-lookup contract used by PortAllocator to avoid known collisions."""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class PortLookupProtocol(Protocol):
    """Read-only source of already-assigned host ports."""

    def list_assigned_ports(self) -> tuple[int, ...]:
        """Return host ports already assigned to active provisioned engines."""
        ...
