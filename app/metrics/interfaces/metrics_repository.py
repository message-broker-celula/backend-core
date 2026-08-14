"""Public metrics repository contract."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class MetricsRepositoryProtocol(Protocol):
    """Persistence contract for platform-wide public metrics (fn_MetricasPublicas)."""

    def get_public_metrics(self) -> Mapping[str, Any]:
        """Return aggregate platform metrics for the public landing page."""
        ...
