from datetime import datetime

from pydantic import BaseModel, Field, model_validator

from app.schemas.attachment import AttachmentOut
from app.schemas.common import OrmModel


class MessageCreate(BaseModel):
    conversation_id: str
    client_message_id: str = Field(min_length=1, max_length=100)
    text: str | None = Field(default=None, max_length=4000)
    attachment_ids: list[str] = Field(default_factory=list, max_length=5)

    @model_validator(mode="after")
    def validate_content(self) -> "MessageCreate":
        if not (self.text and self.text.strip()) and not self.attachment_ids:
            raise ValueError("Message text or attachment is required")
        if self.text:
            self.text = self.text.strip()
        return self


class MessageOut(OrmModel):
    id: str
    conversation_id: str
    sender_id: str
    client_message_id: str | None = None
    text: str | None
    created_at: datetime
    updated_at: datetime
    edited_at: datetime | None
    deleted_at: datetime | None
    deleted_by_id: str | None
    attachments: list[AttachmentOut] = Field(default_factory=list)
    read_by: list[str] = Field(default_factory=list)


class MessageHistory(BaseModel):
    items: list[MessageOut]
    next_cursor: str | None = None
    has_more: bool = False


class MessageReadEvent(BaseModel):
    conversation_id: str
    user_id: str
    read_at: datetime
    message_ids: list[str]
