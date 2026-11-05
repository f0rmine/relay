from datetime import datetime

from pydantic import BaseModel, Field, field_validator

from app.core.security import sign_avatar_url
from app.schemas.message import MessageOut
from app.schemas.user import UserSearchResult


class ConversationCreate(BaseModel):
    participant_id: str


class GroupCreate(BaseModel):
    title: str = Field(min_length=1, max_length=120)
    participant_ids: list[str] = Field(min_length=2, max_length=100)


class GroupUpdate(BaseModel):
    title: str = Field(min_length=1, max_length=120)


class ParticipantIdsRequest(BaseModel):
    participant_ids: list[str] = Field(min_length=1, max_length=100)


class ConversationOut(BaseModel):
    id: str
    kind: str = "private"
    title: str | None = None
    avatar_url: str | None = None
    is_admin: bool = False
    admin_ids: list[str] = Field(default_factory=list)
    participants: list[UserSearchResult]
    latest_message: MessageOut | None = None
    pinned_message_id: str | None = None
    unread_count: int = 0
    first_unread_id: str | None = None
    created_at: datetime
    updated_at: datetime

    @field_validator("avatar_url", mode="after")
    @classmethod
    def sign_avatar(cls, value: str | None) -> str | None:
        return sign_avatar_url(value)


class ConversationDetail(ConversationOut):
    pass
