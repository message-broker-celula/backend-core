"""Deterministic container naming shared by every provisioning operation.

SQL Server already stores the host `puerto` assigned to each provisioned
database instance -- deriving the container name from that port means no new
persistent state is needed anywhere to answer "which container belongs to
this database instance."
"""

from __future__ import annotations


def container_name_for_port(port: int) -> str:
    """Return the deterministic container name for a given host port."""

    return f"dbinst-{port}"
