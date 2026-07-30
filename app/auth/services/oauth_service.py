"""OAuth provider orchestration.

This module is responsible for the thin HTTP-facing OAuth coordination layer.
It builds provider authorization URLs, validates state, exchanges authorization
codes for access tokens, and normalizes provider responses into the common
`OAuthUserIdentity` contract.
"""

from __future__ import annotations

import json
import logging
import secrets
import time
from base64 import urlsafe_b64decode, urlsafe_b64encode
from binascii import Error as BinasciiError
from collections.abc import Mapping
from hashlib import sha256
from hmac import compare_digest, new as hmac_new
from typing import Literal
from urllib import error, request
from urllib.parse import urlencode

from app.auth.exceptions.auth_exceptions import OAuthStateError
from app.auth.schemas.auth_schemas import OAuthUserIdentity
from app.core.config import GithubSettings, GoogleSettings, settings

ProviderName = Literal["google", "github"]
HTTP_TIMEOUT_SECONDS = 10
STATE_VERSION = "v1"
STATE_MAX_FUTURE_SKEW_SECONDS = 60

logger = logging.getLogger(__name__)


class OAuthHttpClient:
    """HTTP client abstraction for OAuth provider calls."""

    def post_json(
        self,
        url: str,
        data: Mapping[str, str],
        headers: Mapping[str, str] | None = None,
    ) -> Mapping[str, object]:
        """Perform a form-encoded POST and return a JSON object.

        Args:
            url: Provider token endpoint.
            data: Form-encoded token exchange parameters.
            headers: Optional request headers.

        Returns:
            Mapping[str, object]: Parsed JSON object.
        """

        encoded_data = urlencode(data).encode("utf-8")
        request_obj = request.Request(
            url=url,
            data=encoded_data,
            headers={
                "Accept": "application/json",
                "Content-Type": "application/x-www-form-urlencoded",
                **dict(headers or {}),
            },
            method="POST",
        )

        try:
            with request.urlopen(request_obj, timeout=HTTP_TIMEOUT_SECONDS) as response:
                body = response.read().decode("utf-8")
        except (error.HTTPError, error.URLError, TimeoutError) as exc:
            raise OAuthStateError("OAuth provider token exchange failed") from exc

        return self._parse_json_object(body, "Invalid provider token response")

    def get_json(
        self,
        url: str,
        headers: Mapping[str, str] | None = None,
    ) -> Mapping[str, object] | list[object]:
        """Perform a GET and return a JSON object or list.

        Args:
            url: Provider endpoint.
            headers: Optional request headers.

        Returns:
            Mapping[str, object] | list[object]: Parsed JSON payload.
        """

        request_obj = request.Request(
            url=url,
            headers={"Accept": "application/json", **dict(headers or {})},
            method="GET",
        )

        try:
            with request.urlopen(request_obj, timeout=HTTP_TIMEOUT_SECONDS) as response:
                body = response.read().decode("utf-8")
        except (error.HTTPError, error.URLError, TimeoutError) as exc:
            raise OAuthStateError("OAuth provider user-info request failed") from exc

        try:
            parsed_body = json.loads(body)
        except json.JSONDecodeError as exc:
            raise OAuthStateError("Invalid provider user-info response") from exc
        if not isinstance(parsed_body, (dict, list)):
            raise OAuthStateError("Invalid provider user-info response")
        return parsed_body

    def _parse_json_object(self, body: str, error_message: str) -> Mapping[str, object]:
        """Parse a JSON object and raise a sanitized OAuth error on failure."""

        try:
            parsed_body = json.loads(body)
        except json.JSONDecodeError as exc:
            raise OAuthStateError(error_message) from exc
        if not isinstance(parsed_body, dict):
            raise OAuthStateError(error_message)
        return parsed_body


class OAuthService:
    """Coordinate provider OAuth handshakes without embedding business logic.

    This service is intentionally thin and remains responsible only for:
    - generating and validating OAuth state values,
    - performing provider token/user-info exchanges,
    - normalizing provider-specific payloads into a shared DTO.
    """

    def __init__(self, http_client: OAuthHttpClient | None = None) -> None:
        """Initialize the OAuth service.

        Args:
            http_client: Optional provider HTTP client for tests and alternate
                transports.
        """

        self._http_client = http_client or OAuthHttpClient()

    def generate_state(self, provider: ProviderName) -> str:
        """Generate a signed, time-bounded OAuth state value.

        Args:
            provider: Provider identifier bound into the state signature.

        Returns:
            str: Random state token suitable for CSRF validation.
        """

        issued_at = str(int(time.time()))
        nonce = secrets.token_urlsafe(32)
        signature = self._state_signature(provider=provider, issued_at=issued_at, nonce=nonce)
        return ".".join([STATE_VERSION, issued_at, nonce, signature])

    def build_authorization_url(self, provider: ProviderName) -> str:
        """Build a provider authorization URL for the start of the OAuth flow.

        Args:
            provider: Provider identifier.

        Returns:
            str: Fully formed authorize URL.

        Raises:
            OAuthStateError: When the provider configuration is incomplete.
        """

        provider_settings = self._get_provider_settings(provider)
        self._validate_provider_settings(provider, provider_settings)
        params = self._authorization_params(provider, provider_settings)
        return f"{provider_settings.authorize_url}?{urlencode(params)}"

    def build_authorization_url_with_state(
        self,
        provider: ProviderName,
        state: str,
    ) -> str:
        """Build a provider authorization URL including the CSRF state value.

        Args:
            provider: Provider identifier.
            state: State token to preserve in the redirect.

        Returns:
            str: Authorization URL with the state parameter.
        """

        provider_settings = self._get_provider_settings(provider)
        self._validate_provider_settings(provider, provider_settings)
        params = self._authorization_params(provider, provider_settings, state=state)
        return f"{provider_settings.authorize_url}?{urlencode(params)}"

    def validate_state(
        self,
        provider: ProviderName,
        state: str | None,
        cookie_state: str | None,
    ) -> None:
        """Validate the provider state token against the secure cookie value.

        Args:
            provider: Provider identifier.
            state: State supplied by the provider callback.
            cookie_state: State stored in the secure cookie.

        Raises:
            OAuthStateError: When the state payload is missing, mismatched, or
                expired.
        """

        if not state or not cookie_state:
            raise OAuthStateError(f"Invalid OAuth state for provider '{provider}'")
        if not compare_digest(state, cookie_state):
            raise OAuthStateError(f"OAuth state mismatch for provider '{provider}'")
        self._validate_signed_state(provider, state)

    def exchange_code_for_identity(
        self,
        provider: ProviderName,
        code: str,
        redirect_uri: str,
    ) -> OAuthUserIdentity:
        """Exchange the authorization code for a normalized provider identity.

        Args:
            provider: Provider identifier.
            code: Authorization code returned by the provider callback.
            redirect_uri: Callback redirect URI.

        Returns:
            OAuthUserIdentity: Common identity DTO.

        Raises:
            OAuthStateError: When the provider response is invalid or missing.
        """

        provider_settings = self._get_provider_settings(provider)
        token_payload = self._fetch_provider_token(provider, code, redirect_uri, provider_settings)
        access_token = token_payload.get("access_token")

        if not isinstance(access_token, str) or not access_token:
            raise OAuthStateError(f"Missing access token for provider '{provider}'")

        user_payload = self._fetch_provider_user_info(provider, access_token, provider_settings)

        if provider == "google":
            return self._normalize_google_identity(user_payload)

        identity = self._normalize_github_identity(user_payload)
        if identity.email:
            return identity

        email = self._fetch_github_primary_email(access_token, provider_settings)
        return identity.model_copy(update={"email": email, "verified_email": email is not None})

    def _authorization_params(
        self,
        provider: ProviderName,
        provider_settings: GoogleSettings | GithubSettings,
        state: str | None = None,
    ) -> dict[str, str]:
        """Build provider-specific authorization parameters."""

        params = {
            "client_id": provider_settings.client_id,
            "redirect_uri": provider_settings.redirect_uri,
            "response_type": "code",
            "scope": self._provider_scope(provider),
        }
        if state:
            params["state"] = state
        if provider == "google":
            params["access_type"] = "offline"
            params["prompt"] = "consent"
        return params

    def _provider_scope(self, provider: ProviderName) -> str:
        """Return the provider-specific OAuth scope.

        Args:
            provider: Provider identifier.

        Returns:
            str: Scope string for the authorize request.
        """

        if provider == "google":
            return "openid email profile"
        return "read:user user:email"

    def _get_provider_settings(self, provider: ProviderName) -> GoogleSettings | GithubSettings:
        """Return the provider configuration payload from settings."""

        provider_config = settings.oauth
        if provider == "google":
            return provider_config.google
        return provider_config.github

    def _validate_provider_settings(
        self,
        provider: ProviderName,
        provider_settings: GoogleSettings | GithubSettings,
    ) -> None:
        """Validate required provider configuration without exposing secrets."""

        required_values = {
            "client_id": provider_settings.client_id,
            "client_secret": provider_settings.client_secret,
            "redirect_uri": provider_settings.redirect_uri,
            "authorize_url": provider_settings.authorize_url,
            "token_url": provider_settings.token_url,
            "userinfo_url": provider_settings.userinfo_url,
        }
        if provider == "github":
            required_values["emails_url"] = provider_settings.emails_url

        missing = [
            key
            for key, value in required_values.items()
            if not (value.get_secret_value() if hasattr(value, "get_secret_value") else value)
        ]
        if missing:
            logger.error("OAuth provider configuration is incomplete", extra={"provider": provider})
            raise OAuthStateError(f"OAuth provider '{provider}' is not configured")

    def _fetch_provider_token(
        self,
        provider: ProviderName,
        code: str,
        redirect_uri: str,
        provider_settings: GoogleSettings | GithubSettings,
    ) -> Mapping[str, object]:
        """Fetch an access token from a provider token endpoint."""

        data = {
            "code": code,
            "client_id": provider_settings.client_id,
            "client_secret": provider_settings.client_secret.get_secret_value(),
            "redirect_uri": redirect_uri,
            "grant_type": "authorization_code",
        }

        token_response = self._http_client.post_json(
            url=provider_settings.token_url,
            data=data,
        )

        if not isinstance(token_response, dict):
            raise OAuthStateError(f"Invalid token response for provider '{provider}'")

        return token_response

    def _fetch_provider_user_info(
        self,
        provider: ProviderName,
        access_token: str,
        provider_settings: GoogleSettings | GithubSettings,
    ) -> Mapping[str, object]:
        """Fetch provider user information."""

        payload = self._http_client.get_json(
            url=provider_settings.userinfo_url,
            headers={"Authorization": f"Bearer {access_token}"},
        )
        if not isinstance(payload, dict):
            raise OAuthStateError(f"Invalid user profile response for provider '{provider}'")

        return payload

    def _fetch_github_primary_email(
        self,
        access_token: str,
        provider_settings: GithubSettings,
    ) -> str | None:
        """Fetch the verified primary GitHub email when the profile omits it."""

        payload = self._http_client.get_json(
            url=provider_settings.emails_url,
            headers={"Authorization": f"Bearer {access_token}"},
        )
        if not isinstance(payload, list):
            raise OAuthStateError("Invalid GitHub email response")

        for item in payload:
            if not isinstance(item, dict):
                continue
            email = item.get("email")
            if (
                isinstance(email, str)
                and item.get("primary") is True
                and item.get("verified") is True
            ):
                return email
        return None

    def _normalize_google_identity(self, payload: Mapping[str, object]) -> OAuthUserIdentity:
        """Normalize the Google user-info payload into the common DTO."""

        provider_user_id = payload.get("sub")
        if not isinstance(provider_user_id, str) or not provider_user_id:
            raise OAuthStateError("Google profile response did not contain a valid user identifier")

        email = payload.get("email")
        if not isinstance(email, str):
            email = None

        name = payload.get("name")
        if not isinstance(name, str):
            name = None

        avatar = payload.get("picture")
        if not isinstance(avatar, str):
            avatar = None

        verified_email = payload.get("email_verified")
        verified_email_bool = verified_email is True

        return OAuthUserIdentity(
            provider="google",
            provider_user_id=provider_user_id,
            email=email,
            name=name,
            avatar=avatar,
            verified_email=verified_email_bool,
        )

    def _normalize_github_identity(self, payload: Mapping[str, object]) -> OAuthUserIdentity:
        """Normalize the GitHub user-info payload into the common DTO."""

        provider_user_id = payload.get("id")
        if not isinstance(provider_user_id, str | int):
            raise OAuthStateError("GitHub profile response did not contain a valid user identifier")

        email = payload.get("email")
        if not isinstance(email, str):
            email = None

        name = payload.get("name")
        if not isinstance(name, str):
            name = payload.get("login")
        if not isinstance(name, str):
            name = None

        avatar = payload.get("avatar_url")
        if not isinstance(avatar, str):
            avatar = None

        return OAuthUserIdentity(
            provider="github",
            provider_user_id=str(provider_user_id),
            email=email,
            name=name,
            avatar=avatar,
            verified_email=False,
        )

    def _state_signature(self, provider: ProviderName, issued_at: str, nonce: str) -> str:
        """Create a URL-safe HMAC signature for an OAuth state token."""

        secret = settings.jwt.secret_key.get_secret_value().encode("utf-8")
        message = f"{provider}:{issued_at}:{nonce}".encode("utf-8")
        digest = hmac_new(secret, message, sha256).digest()
        return urlsafe_b64encode(digest).decode("ascii").rstrip("=")

    def _validate_signed_state(self, provider: ProviderName, state: str) -> None:
        """Validate state format, signature, and expiration."""

        parts = state.split(".")
        if len(parts) != 4 or parts[0] != STATE_VERSION:
            raise OAuthStateError(f"Invalid OAuth state for provider '{provider}'")

        _, issued_at, nonce, signature = parts
        try:
            issued_at_value = int(issued_at)
        except (BinasciiError, ValueError) as exc:
            raise OAuthStateError(f"Invalid OAuth state for provider '{provider}'") from exc

        now = int(time.time())
        if issued_at_value > now + STATE_MAX_FUTURE_SKEW_SECONDS:
            raise OAuthStateError(f"Invalid OAuth state for provider '{provider}'")
        if now - issued_at_value > settings.oauth.state_ttl_seconds:
            raise OAuthStateError(f"Expired OAuth state for provider '{provider}'")

        try:
            urlsafe_b64decode(nonce + "=" * (-len(nonce) % 4))
        except ValueError as exc:
            raise OAuthStateError(f"Invalid OAuth state for provider '{provider}'") from exc

        expected_signature = self._state_signature(
            provider=provider,
            issued_at=issued_at,
            nonce=nonce,
        )
        if not compare_digest(signature, expected_signature):
            raise OAuthStateError(f"OAuth state signature mismatch for provider '{provider}'")
