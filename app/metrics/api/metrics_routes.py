"""Public metrics HTTP endpoint.

Backs the landing page's public stats section -- unauthenticated by design
(these are meant to be shown to visitors before they log in), polled by the
frontend every 30s.
"""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.core.rate_limit import limiter
from app.metrics.repositories.metrics_repository import MetricsRepository
from app.metrics.schemas.metrics_schemas import PublicMetrics
from app.metrics.services.metrics_service import MetricsService
from app.repositories.exceptions.database_exceptions import DatabaseIntegrationError

router = APIRouter(tags=["Metrics"])
logger = logging.getLogger(__name__)


def get_metrics_service() -> MetricsService:
    """Return the Stored Procedure-backed metrics service dependency."""

    return MetricsService(repository=MetricsRepository())


Service = Annotated[MetricsService, Depends(get_metrics_service)]


@router.get(
    "/metrics",
    response_model=PublicMetrics,
    response_model_by_alias=True,
    summary="Public platform metrics for the landing page",
)
@limiter.limit("60/minute")
def get_public_metrics(request: Request, service: Service) -> PublicMetrics:
    """Return aggregate platform metrics (fn_MetricasPublicas), no auth required."""

    try:
        return service.get_public_metrics()
    except DatabaseIntegrationError as exc:
        logger.error("Public metrics query failed", exc_info=exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Metrics service unavailable",
        ) from exc
