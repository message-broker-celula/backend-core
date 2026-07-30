from datetime import datetime, timezone

from pydantic import BaseModel, ConfigDict, field_validator


class TokenPayload(BaseModel):
    """
    JWT payload after being successfully decoded.
    """

    model_config = ConfigDict(extra="allow")

    sub: str
    iat: datetime | int
    exp: datetime | int
    iss: str | None = None
    aud: str | list[str] | None = None

    @field_validator("iat", "exp", mode="before")
    @classmethod
    def convert_timestamp_claim(cls, value: object) -> object:
        if isinstance(value, (int, float)):
            return datetime.fromtimestamp(value, tz=timezone.utc)
        return value
