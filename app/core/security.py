from datetime import datetime, timedelta, timezone
from typing import Any

from jose import jwt

from app.core.config import settings
from app.core.schemas.token import TokenPayload

JWT_RESERVED_CLAIMS = frozenset(
    {
        "sub",
        "iat",
        "exp",
        "iss",
        "aud",
        "nbf",
        "jti",
    }
)


def create_access_token(
    subject: str,
    additional_claims: dict[str, Any] | None = None,
    expires_minutes: int | None = None,
) -> str:
    """
    Generate a signed JWT access token.

    Args:
        subject: Unique identifier of the authenticated user.
        additional_claims: Extra claims to include in the payload.
        expires_minutes: Optional custom lifetime in minutes.

    Returns:
        Encoded JWT access token
    """
    issued_at = datetime.now(timezone.utc)
    expires_at = issued_at + timedelta(
        minutes=expires_minutes or settings.jwt.expire_minutes,
    )

    payload = {
        "sub": subject,
        "iat": issued_at,
        "exp": expires_at,
    }
    if settings.jwt.issuer:
        payload["iss"] = settings.jwt.issuer
    if settings.jwt.audience:
        payload["aud"] = settings.jwt.audience

    if additional_claims:
        filtered_claims = {
            key: value
            for key, value in additional_claims.items()
            if key not in JWT_RESERVED_CLAIMS
        }
        payload.update(filtered_claims)

    return jwt.encode(
        claims=payload,
        key=settings.jwt.secret_key.get_secret_value(),
        algorithm=settings.jwt.algorithm,
    )


def decode_access_token(
    token: str,
) -> TokenPayload:
    """
    Decode and validate a JWT access token.

    Args:
        token: Encoded JWT access token.

    Returns:
        Decoded and validated JWT payload.

    Raises:
        JWTError: If the token is invalid or expired.
    """

    decode_options = {"verify_aud": bool(settings.jwt.audience)}
    decode_kwargs: dict[str, Any] = {"options": decode_options}
    if settings.jwt.issuer:
        decode_kwargs["issuer"] = settings.jwt.issuer
    if settings.jwt.audience:
        decode_kwargs["audience"] = settings.jwt.audience

    decoded_payload = jwt.decode(
        token=token,
        key=settings.jwt.secret_key.get_secret_value(),
        algorithms=[settings.jwt.algorithm],
        **decode_kwargs,
    )

    return TokenPayload.model_validate(decoded_payload)
