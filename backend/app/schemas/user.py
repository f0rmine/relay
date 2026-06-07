from datetime import datetime

from pydantic import BaseModel, EmailStr, Field, field_validator

from app.schemas.common import OrmModel


class UserPublic(OrmModel):
    id: str
    username: str
    email: EmailStr | None = None
    display_name: str
    avatar_url: str | None = None
    created_at: datetime
    last_seen_at: datetime | None = None
    is_online: bool = False


class UserSearchResult(BaseModel):
    id: str
    username: str
    display_name: str
    avatar_url: str | None = None
    last_seen_at: datetime | None = None
    is_online: bool = False


class ProfileUpdate(BaseModel):
    display_name: str | None = Field(default=None, min_length=1, max_length=80)
    email: EmailStr | None = None

    @field_validator("display_name")
    @classmethod
    def normalize_display_name(cls, value: str | None) -> str | None:
        if value is None:
            return value
        normalized = value.strip()
        if not normalized:
            raise ValueError("Display name is required")
        return normalized
