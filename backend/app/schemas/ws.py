from typing import Any

from pydantic import BaseModel, Field


class WebSocketEnvelope(BaseModel):
    type: str
    payload: dict[str, Any] = Field(default_factory=dict)


class AuthPayload(BaseModel):
    token: str


class ConversationIdPayload(BaseModel):
    conversation_id: str


class TypingPayload(BaseModel):
    conversation_id: str


class MessageSendPayload(BaseModel):
    conversation_id: str
    text: str | None = Field(default=None, max_length=4000)
    attachment_ids: list[str] = Field(default_factory=list, max_length=5)


class MessageDeletePayload(BaseModel):
    message_id: str


class ServerEvent(BaseModel):
    type: str
    payload: dict[str, Any]
