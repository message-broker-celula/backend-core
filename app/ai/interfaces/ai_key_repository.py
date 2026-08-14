"""AI Gateway key repository contract."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class AiKeyRepositoryProtocol(Protocol):
    """Persistence contract for encrypted AI Gateway API keys (ClavesIA)."""

    def get_user_profile(self, subject: str) -> Mapping[str, Any]:
        """Return the caller's own nombre/correo (fn_ObtenerPerfilUsuario)."""
        ...

    def register_ai_key(
        self,
        subject: str,
        gateway_client_id: int,
        key_prefix: str,
        api_key: str,
        ip: str | None = None,
    ) -> Mapping[str, Any]:
        """Persist a newly-issued gateway key, encrypted (sp_RegistrarClaveIA)."""
        ...

    def get_ai_key(self, subject: str) -> Mapping[str, Any]:
        """Return the caller's own active, decrypted gateway key (sp_ObtenerClaveIA)."""
        ...

    def rotate_ai_key(
        self,
        subject: str,
        gateway_client_id: int,
        key_prefix: str,
        api_key: str,
        ip: str | None = None,
    ) -> None:
        """Replace the caller's active key with a freshly-rotated one (sp_RotarClaveIA)."""
        ...

    def revoke_ai_key(self, subject: str, ip: str | None = None) -> None:
        """Mark the caller's active gateway key as revoked (sp_RevocarClaveIA)."""
        ...
