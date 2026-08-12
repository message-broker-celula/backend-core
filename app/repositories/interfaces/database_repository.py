"""Broad, database-centric repository contract.

This protocol enumerates every Stored Procedure/View/Function operation the
platform exposes. `SQLServerRepository` is the single concrete class that
satisfies it (structurally -- no explicit inheritance needed, per DIP). Each
domain module (auth, databases, celulas, admin, audit) then defines its OWN
narrow Protocol re-describing only the slice it actually needs, so services
never depend on this broad interface directly.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Protocol, runtime_checkable

from app.auth.schemas.auth_schemas import (
    OAuthRegistrationResult,
    OAuthUserIdentity,
    RefreshTokenResult,
)


@runtime_checkable
class DatabaseRepositoryProtocol(Protocol):
    """Every Stored Procedure/View/Function operation, in one contract."""

    # -- Authentication --------------------------------------------------
    def register_oauth_user(
        self,
        provider: str,
        identity: OAuthUserIdentity,
        ip: str | None = None,
        user_agent: str | None = None,
    ) -> OAuthRegistrationResult: ...

    def issue_refresh_token(
        self,
        subject: str,
        ip: str | None = None,
        user_agent: str | None = None,
        validity_days: int = 30,
    ) -> str: ...

    def refresh_access_token(
        self,
        refresh_token: str,
        ip: str | None = None,
        user_agent: str | None = None,
        validity_days: int = 30,
    ) -> RefreshTokenResult: ...

    def revoke_refresh_token(self, refresh_token: str, ip: str | None = None) -> None: ...

    def revoke_all_refresh_tokens(self, subject: str, ip: str | None = None) -> None: ...

    # -- Databases ---------------------------------------------------------
    def create_database(self, subject: str, payload: Mapping[str, Any], ip: str | None) -> str: ...

    def get_database_credentials(self, subject: str, database_id: str | None = None) -> dict[str, str]: ...

    def list_databases(self, subject: str) -> tuple[dict[str, Any], ...]: ...

    def get_database(self, subject: str, database_id: str) -> Mapping[str, Any]: ...

    def delete_database(self, subject: str, database_id: str, ip: str | None = None) -> None: ...

    def get_database_usage(self, subject: str, database_id: str) -> Mapping[str, Any]: ...

    def pause_database(self, subject: str, database_id: str, ip: str | None = None) -> None: ...

    def resume_database(self, subject: str, database_id: str) -> None: ...

    def register_activity(self, database_id: str, ttl_days: int = 30) -> None: ...

    def update_space(
        self,
        database_id: str,
        reported_space_mb: float,
        ip: str | None,
        ttl_days: int = 30,
    ) -> bool: ...

    def validate_connection(self, database_id: str) -> bool: ...

    def release_connection(self, database_id: str) -> None: ...

    def get_ttl_days_remaining(self, database_id: str) -> int | None: ...

    def get_space_percentage(self, database_id: str) -> float | None: ...

    def register_event(
        self,
        event: str,
        subject: str | None,
        database_id: str | None,
        description: str,
        ip: str | None,
        result: str,
        additional_data: str | None = None,
    ) -> None: ...

    # -- Administration ------------------------------------------------------
    def list_users(
        self,
        requester_id: str | None = None,
        page: int = 1,
        page_size: int = 50,
    ) -> tuple[dict[str, Any], ...]: ...

    def update_user_role(
        self,
        requester_id: str,
        user_id: str,
        role: str,
        ip: str | None = None,
    ) -> None: ...

    def list_all_databases(
        self,
        requester_id: str | None = None,
        page: int = 1,
        page_size: int = 50,
        status_filter: str | None = None,
    ) -> tuple[dict[str, Any], ...]: ...

    # -- Celulas and services ------------------------------------------------
    def create_celula(self, subject: str, name: str, ip: str | None = None) -> Mapping[str, Any]: ...

    def list_celulas(self, subject: str) -> tuple[dict[str, Any], ...]: ...

    def get_celula(self, subject: str, celula_id: str) -> Mapping[str, Any]: ...

    def register_celula_service(
        self,
        subject: str,
        celula_id: str,
        service_name: str,
        service_type: str,
        database_id: str | None,
        port: int | None = None,
        ip: str | None = None,
    ) -> Mapping[str, Any]: ...

    def list_celula_services(self, subject: str, celula_id: str) -> tuple[dict[str, Any], ...]: ...

    def delete_celula_service(self, subject: str, celula_id: str, service_id: str) -> None: ...

    def change_service_status(
        self,
        subject: str,
        service_id: str,
        new_status: str,
        ip: str | None,
    ) -> None: ...
