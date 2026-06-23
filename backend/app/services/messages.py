import base64
import binascii
import json
from datetime import UTC, datetime
from uuid import uuid4

from fastapi import HTTPException, status
from sqlalchemy import and_, desc, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.encryption import (
    DecryptionError,
    ENCRYPTION_VERSION,
    get_encryption_keyring,
    message_text_associated_data,
)
from app.models.attachment import Attachment
from app.models.message import Message
from app.models.user import User
from app.services.conversations import require_participant

MessageCursor = tuple[datetime, str]


def encode_message_cursor(message: Message) -> str:
    created_at = message.created_at
    if created_at.utcoffset() is None:
        created_at = created_at.replace(tzinfo=UTC)
    payload = json.dumps([created_at.isoformat(), message.id], separators=(",", ":"))
    return base64.urlsafe_b64encode(payload.encode()).decode().rstrip("=")


def decode_message_cursor(cursor: str) -> MessageCursor:
    try:
        padded = cursor + "=" * (-len(cursor) % 4)
        created_at_raw, message_id = json.loads(base64.urlsafe_b64decode(padded).decode())
        created_at = datetime.fromisoformat(created_at_raw)
        if created_at.utcoffset() is None or not isinstance(message_id, str) or not message_id:
            raise ValueError
    except (binascii.Error, ValueError, TypeError, json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid message cursor") from exc
    return created_at, message_id


def plaintext_message_text(message: Message) -> str | None:
    if message.deleted_at is not None:
        return None
    if message.text_ciphertext is None:
        return message.text
    if (
        message.text_nonce is None
        or message.text_key_id is None
        or message.encryption_version is None
    ):
        raise DecryptionError("Encrypted message metadata is incomplete")
    if message.encryption_version != ENCRYPTION_VERSION:
        raise DecryptionError("Unsupported message encryption version")
    plaintext = get_encryption_keyring().decrypt(
        message.text_ciphertext,
        message.text_nonce,
        message.text_key_id,
        associated_data=message_text_associated_data(message.id),
    )
    try:
        return plaintext.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise DecryptionError("Invalid encrypted message text") from exc


async def create_message(
    db: AsyncSession,
    user: User,
    conversation_id: str,
    text: str | None,
    attachment_ids: list[str] | None = None,
) -> Message:
    attachment_ids = attachment_ids or []
    await require_participant(db, conversation_id, user.id)
    if not (text and text.strip()) and not attachment_ids:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Message text or attachment is required")
    attachments: list[Attachment] = []
    if attachment_ids:
        attachments = list(
            (
                await db.scalars(
                    select(Attachment).where(
                        Attachment.id.in_(attachment_ids),
                        Attachment.uploader_id == user.id,
                        Attachment.message_id.is_(None),
                    )
                )
            ).all()
        )
        if len(attachments) != len(set(attachment_ids)):
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid attachment")
    now = datetime.now(UTC)
    message_id = str(uuid4())
    normalized_text = text.strip() if text else None
    encrypted_text = (
        get_encryption_keyring().encrypt(
            normalized_text.encode("utf-8"),
            associated_data=message_text_associated_data(message_id),
        )
        if normalized_text
        else None
    )
    message = Message(
        id=message_id,
        conversation_id=conversation_id,
        sender_id=user.id,
        text=None,
        text_ciphertext=encrypted_text.ciphertext if encrypted_text else None,
        text_nonce=encrypted_text.nonce if encrypted_text else None,
        text_key_id=encrypted_text.key_id if encrypted_text else None,
        encryption_version=encrypted_text.version if encrypted_text else None,
        created_at=now,
        updated_at=now,
    )
    db.add(message)
    await db.flush()
    if attachment_ids:
        for attachment in attachments:
            attachment.message_id = message.id
    from app.models.conversation import Conversation

    conversation = await db.get(Conversation, conversation_id)
    if conversation:
        conversation.updated_at = datetime.now(UTC)
    await db.commit()
    await db.refresh(message, attribute_names=["attachments", "reads"])
    return message


async def list_messages(
    db: AsyncSession,
    user_id: str,
    conversation_id: str,
    cursor: MessageCursor | None = None,
    limit: int = 30,
) -> tuple[list[Message], bool]:
    await require_participant(db, conversation_id, user_id)
    stmt = (
        select(Message)
        .options(selectinload(Message.attachments), selectinload(Message.reads))
        .where(Message.conversation_id == conversation_id)
        .order_by(desc(Message.created_at), desc(Message.id))
        .limit(limit + 1)
    )
    if cursor is not None:
        cursor_created_at, cursor_id = cursor
        stmt = stmt.where(
            or_(
                Message.created_at < cursor_created_at,
                and_(Message.created_at == cursor_created_at, Message.id < cursor_id),
            )
        )
    rows = list((await db.scalars(stmt)).unique().all())
    return rows[:limit], len(rows) > limit


async def delete_message_for_everyone(db: AsyncSession, message_id: str, user: User) -> Message:
    message = (
        await db.scalars(
            select(Message)
            .options(selectinload(Message.attachments), selectinload(Message.reads))
            .where(Message.id == message_id)
        )
    ).first()
    if message is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Message not found")
    await require_participant(db, message.conversation_id, user.id)
    if message.sender_id != user.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only sender can delete this message")
    now = datetime.now(UTC)
    message.deleted_at = now
    message.updated_at = now
    message.deleted_by_id = user.id
    message.text = None
    message.text_ciphertext = None
    message.text_nonce = None
    message.text_key_id = None
    message.encryption_version = None
    await db.commit()
    await db.refresh(message, attribute_names=["attachments", "reads"])
    return message
