from typing import Any

from pydantic import BaseModel, Field


class WebSocketEnvelope(BaseModel):
    type: str
    payload: dict[str, Any] = Field(default_factory=dict)
    request_id: str | None = Field(default=None, min_length=1, max_length=100)


class AuthPayload(BaseModel):
    token: str


class ConversationIdPayload(BaseModel):
    conversation_id: str


class TypingPayload(BaseModel):
    conversation_id: str


class MessageSendPayload(BaseModel):
    conversation_id: str
    client_message_id: str | None = Field(default=None, min_length=1, max_length=100)
    text: str | None = Field(default=None, max_length=4000)
    attachment_ids: list[str] = Field(default_factory=list, max_length=5)


class MessageDeletePayload(BaseModel):
    message_id: str


class ServerEvent(BaseModel):
    type: str
    payload: dict[str, Any]
