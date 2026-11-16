from datetime import UTC, datetime, timedelta

from pydantic import BaseModel, Field, model_validator

from app.schemas.attachment import AttachmentOut
from app.schemas.common import OrmModel

DEVICE_ID_PATTERN = r"^[A-Za-z0-9_-]+$"
# A padded 4000-char message plus the PQXDH prekey header stays well under this.
MAX_ENVELOPE_CHARS = 16384


class EnvelopeIn(BaseModel):
    user_id: str = Field(min_length=1, max_length=36)
    device_id: str = Field(min_length=8, max_length=64, pattern=DEVICE_ID_PATTERN)
    ciphertext: str = Field(min_length=1, max_length=MAX_ENVELOPE_CHARS, pattern=DEVICE_ID_PATTERN)


class MessageCreate(BaseModel):
    conversation_id: str
    client_message_id: str = Field(min_length=1, max_length=100)
    text: str | None = Field(default=None, max_length=4000)
    attachment_ids: list[str] = Field(default_factory=list, max_length=5)
    reply_to_id: str | None = Field(default=None, max_length=36)
    scheduled_at: datetime | None = None
    mentions: list[str] = Field(default_factory=list, max_length=50)
    # End-to-end encrypted messages: one envelope per recipient device, no text.
    envelopes: list[EnvelopeIn] | None = Field(default=None, max_length=100)
    sender_device_id: str | None = Field(
        default=None, min_length=8, max_length=64, pattern=DEVICE_ID_PATTERN
    )

    @model_validator(mode="after")
    def validate_content(self) -> "MessageCreate":
        if self.envelopes is not None:
            if not self.sender_device_id:
                raise ValueError("sender_device_id is required for encrypted messages")
            if self.text or self.attachment_ids or self.mentions:
                raise ValueError("Encrypted messages carry content only inside envelopes")
        else:
            if not (self.text and self.text.strip()) and not self.attachment_ids:
                raise ValueError("Message text or attachment is required")
            if self.text:
                self.text = self.text.strip()
        if self.scheduled_at is not None:
            scheduled = self.scheduled_at
            if scheduled.tzinfo is None:
                scheduled = scheduled.replace(tzinfo=UTC)
                self.scheduled_at = scheduled
            if scheduled - datetime.now(UTC) > timedelta(days=30):
                raise ValueError("Scheduled messages must be within 30 days")
        return self


class ReactionOut(BaseModel):
    emoji: str
    user_ids: list[str] = Field(default_factory=list)


class ReplyToOut(BaseModel):
    id: str
    text: str | None = None
    sender_id: str
    undecryptable: bool = False


class MessageOut(OrmModel):
    id: str
    conversation_id: str
    sender_id: str
    client_message_id: str | None = None
    text: str | None
    undecryptable: bool = False
    created_at: datetime
    updated_at: datetime
    edited_at: datetime | None
    deleted_at: datetime | None
    deleted_by_id: str | None
    attachments: list[AttachmentOut] = Field(default_factory=list)
    read_by: list[str] = Field(default_factory=list)
    reactions: list[ReactionOut] = Field(default_factory=list)
    reply_to: ReplyToOut | None = None
    scheduled_at: datetime | None = None
    mentions: list[str] = Field(default_factory=list)
    link_preview: dict | None = None
    expires_at: datetime | None = None
    e2ee: bool = False
    sender_device_id: str | None = None
    # The requesting device's envelope (history) or every device's envelope for
    # the receiving user (live events), keyed by device id.
    envelope: str | None = None
    envelopes: dict[str, str] | None = None


class MessageEdit(BaseModel):
    text: str = Field(min_length=1, max_length=4000)

    @model_validator(mode="after")
    def validate_content(self) -> "MessageEdit":
        stripped = self.text.strip()
        if not stripped:
            raise ValueError("Message text cannot be empty")
        self.text = stripped
        return self


class MessageHistory(BaseModel):
    items: list[MessageOut]
    next_cursor: str | None = None
    has_more: bool = False


class MessageReadEvent(BaseModel):
    conversation_id: str
    user_id: str
    read_at: datetime
    message_ids: list[str]
