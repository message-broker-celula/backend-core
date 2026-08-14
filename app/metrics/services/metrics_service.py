"""Public metrics service orchestration."""

from __future__ import annotations

from app.databases.row_mapping import normalize_row, pick_first
from app.metrics.interfaces.metrics_repository import MetricsRepositoryProtocol
from app.metrics.schemas.metrics_schemas import PublicMetrics


class MetricsService:
    """Coordinate public metrics orchestration for the `/metrics` API."""

    def __init__(self, repository: MetricsRepositoryProtocol) -> None:
        self._repository = repository

    def get_public_metrics(self) -> PublicMetrics:
        """Fetch and shape platform-wide public metrics through fn_MetricasPublicas."""

        row = normalize_row(self._repository.get_public_metrics())
        return PublicMetrics(
            totalUsers=int(pick_first(row, "total_users", "total_usuarios") or 0),
            totalDatabases=int(pick_first(row, "total_databases", "total_bases_datos") or 0),
            activeDatabases=int(pick_first(row, "active_databases", "bases_datos_activas") or 0),
            totalLogins=int(pick_first(row, "total_logins") or 0),
            activeUsers=int(pick_first(row, "active_users", "usuarios_activos") or 0),
            availability=float(pick_first(row, "availability", "disponibilidad") or 0.0),
        )
