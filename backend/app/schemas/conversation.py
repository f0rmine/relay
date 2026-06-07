from datetime import datetime

from pydantic import BaseModel

from app.schemas.message import MessageOut
from app.schemas.user import UserSearchResult


class ConversationCreate(BaseModel):
    participant_id: str


class ConversationOut(BaseModel):
    id: str
    kind: str = "private"
    participants: list[UserSearchResult]
    latest_message: MessageOut | None = None
    unread_count: int = 0
    created_at: datetime
    updated_at: datetime


class ConversationDetail(ConversationOut):
    pass
