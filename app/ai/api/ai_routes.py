"""AI-as-a-service key management HTTP endpoints.

Orchestrates the Ollama Gateway (a separate team's already-built, OpenAI-
compatible service) on behalf of the authenticated platform user: issue,
check status, rotate, revoke, and view usage for their own gateway API key.
Actual inference calls (`/v1/chat/completions`, etc.) are never proxied
through this backend -- the end user's own application talks directly to
the gateway using the returned `base_url` and the OpenAI SDK.
"""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status

from app.ai.clients.ollama_gateway_client import OllamaGatewayClient
from app.ai.repositories.ai_key_repository import AiKeyRepository
from app.ai.schemas.ai_schemas import (
    AiKeyActionResponse,
    AiKeyIssuedResponse,
    AiKeyStatusResponse,
    AiUsageResponse,
    RegisterAiKeyRequest,
)
from app.ai.services.ai_key_service import AiKeyService
from app.auth.dependencies.auth_dependencies import get_current_user
from app.auth.schemas.auth_schemas import AuthenticatedUser
from app.core.config import settings
from app.repositories.exceptions.database_exceptions import (
    BusinessRuleViolationError,
    DatabaseIntegrationError,
)

router = APIRouter(prefix="/ai", tags=["AI Gateway"])
logger = logging.getLogger(__name__)


def get_ai_key_service() -> AiKeyService:
    """Return the Stored Procedure + Ollama Gateway-backed AI key service dependency."""

    gateway_settings = settings.ai_gateway
    client = OllamaGatewayClient(
        base_url=gateway_settings.base_url,
        timeout=gateway_settings.request_timeout_seconds,
    )
    return AiKeyService(
        repository=AiKeyRepository(),
        gateway=client,
        gateway_base_url=gateway_settings.base_url,
    )


CurrentUser = Annotated[AuthenticatedUser, Depends(get_current_user)]
Service = Annotated[AiKeyService, Depends(get_ai_key_service)]


def _unavailable(exc: Exception) -> HTTPException:
    logger.error("AI Gateway service call failed", exc_info=exc)
    return HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="AI Gateway service unavailable",
    )


def _business_error(exc: BusinessRuleViolationError) -> HTTPException:
    return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=exc.detail)


@router.post(
    "/api-key",
    response_model=AiKeyIssuedResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Issue a new AI Gateway API key for the authenticated user",
    description=(
        "The raw api_key is only ever shown in this response (and in the "
        "response of /rotate) -- it is stored encrypted, never logged, "
        "never returned again afterward."
    ),
)
def issue_api_key(
    request: Request,
    payload: RegisterAiKeyRequest,
    current_user: CurrentUser,
    service: Service,
) -> AiKeyIssuedResponse:
    """Register a new gateway client for the authenticated user."""

    try:
        return service.issue_key(
            current_user.subject,
            payload.organization,
            payload.intended_use,
            request.client.host if request.client else None,
        )
    except BusinessRuleViolationError as exc:
        raise _business_error(exc) from exc
    except DatabaseIntegrationError as exc:
        raise _unavailable(exc) from exc


@router.get(
    "/api-key",
    response_model=AiKeyStatusResponse,
    summary="Get the authenticated user's AI Gateway key status",
)
def get_api_key_status(current_user: CurrentUser, service: Service) -> AiKeyStatusResponse:
    """Return status/limits for the caller's own active key -- never the raw key."""

    try:
        return service.get_status(current_user.subject)
    except BusinessRuleViolationError as exc:
        raise _business_error(exc) from exc
    except DatabaseIntegrationError as exc:
        raise _unavailable(exc) from exc


@router.post(
    "/api-key/rotate",
    response_model=AiKeyIssuedResponse,
    summary="Rotate the authenticated user's AI Gateway API key",
    description="The old key stops working immediately -- there is no grace period.",
)
def rotate_api_key(
    request: Request,
    current_user: CurrentUser,
    service: Service,
) -> AiKeyIssuedResponse:
    """Rotate the caller's active key, returning the new one."""

    try:
        return service.rotate_key(
            current_user.subject,
            request.client.host if request.client else None,
        )
    except BusinessRuleViolationError as exc:
        raise _business_error(exc) from exc
    except DatabaseIntegrationError as exc:
        raise _unavailable(exc) from exc


@router.delete(
    "/api-key",
    response_model=AiKeyActionResponse,
    summary="Revoke the authenticated user's AI Gateway API key",
)
def revoke_api_key(
    request: Request,
    current_user: CurrentUser,
    service: Service,
) -> AiKeyActionResponse:
    """Revoke the caller's active key."""

    try:
        service.revoke_key(current_user.subject, request.client.host if request.client else None)
    except BusinessRuleViolationError as exc:
        raise _business_error(exc) from exc
    except DatabaseIntegrationError as exc:
        raise _unavailable(exc) from exc
    return AiKeyActionResponse(detail="AI Gateway key revoked")


@router.get(
    "/usage",
    response_model=AiUsageResponse,
    summary="Get the authenticated user's AI Gateway consumption",
)
def get_usage(
    current_user: CurrentUser,
    service: Service,
    start: str | None = Query(default=None, description="UTC date, inclusive (YYYY-MM-DD)."),
    end: str | None = Query(default=None, description="UTC date, inclusive (YYYY-MM-DD)."),
) -> AiUsageResponse:
    """Return the caller's own consumption, proxied from the gateway."""

    try:
        return service.get_usage(current_user.subject, start, end)
    except BusinessRuleViolationError as exc:
        raise _business_error(exc) from exc
    except DatabaseIntegrationError as exc:
        raise _unavailable(exc) from exc
