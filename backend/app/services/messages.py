import asyncio
import base64
import binascii
import json
import logging
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from fastapi import HTTPException, status
from sqlalchemy import and_, desc, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.encryption import (
    ENCRYPTION_VERSION,
    DecryptionError,
    get_encryption_keyring,
    message_text_associated_data,
)
from app.models.attachment import Attachment
from app.models.message import Message, MessageReaction
from app.models.user import User
from app.services.conversations import require_participant

logger = logging.getLogger(__name__)


def visible_messages_clause(now: datetime | None = None):
    """SQLAlchemy clause: message is due and not yet expired."""
    moment = now or datetime.now(UTC)
    return and_(
        or_(Message.scheduled_at.is_(None), Message.scheduled_at <= moment),
        or_(Message.expires_at.is_(None), Message.expires_at > moment),
    )


def parse_mentions(message: Message) -> list[str]:
    raw = message.mentions
    if not raw:
        return []
    try:
        parsed = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return []
    if not isinstance(parsed, list):
        return []
    return [str(item) for item in parsed if isinstance(item, str)]


def is_scheduled_pending(message: Message, now: datetime | None = None) -> bool:
    moment = now or datetime.now(UTC)
    scheduled = message.scheduled_at
    if scheduled is None:
        return False
    if scheduled.tzinfo is None:
        scheduled = scheduled.replace(tzinfo=UTC)
    return scheduled > moment


def _type_mime_filter(message_type: str):
    if message_type == "media":
        return or_(
            Attachment.mime_type.like("image/%"),
            Attachment.mime_type.like("video/%"),
        )
    if message_type == "files":
        return Attachment.mime_type.in_(
            [
                "application/pdf",
                "text/plain",
                "application/msword",
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            ]
        )
    if message_type == "audio":
        return Attachment.mime_type.like("audio/%")
    return None

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
    client_message_id: str | None = None,
    reply_to_id: str | None = None,
    scheduled_at: datetime | None = None,
    mentions: list[str] | None = None,
) -> Message:
    attachment_ids = attachment_ids or []
    conversation = await require_participant(db, conversation_id, user.id)
    if conversation.kind == "private":
        from app.services.blocks import is_blocked

        others = [p.user_id for p in conversation.participants if p.user_id != user.id]
        for other_id in others:
            if await is_blocked(db, user.id, other_id):
                raise HTTPException(status.HTTP_404_NOT_FOUND, "Conversation not found")
    if not (text and text.strip()) and not attachment_ids:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Message text or attachment is required")
    await validate_reply_target(db, conversation_id, reply_to_id)
    if scheduled_at is not None and scheduled_at.tzinfo is None:
        scheduled_at = scheduled_at.replace(tzinfo=UTC)
    participant_ids = {participant.user_id for participant in conversation.participants}
    clean_mentions: list[str] = []
    if mentions:
        for mention_id in dict.fromkeys(mentions):
            if mention_id in participant_ids:
                clean_mentions.append(mention_id)
    mentions_json = json.dumps(clean_mentions) if clean_mentions else None
    attachments: list[Attachment] = []
    if attachment_ids:
        attachments = list(
            (
                await db.scalars(
                    select(Attachment).where(
                        Attachment.id.in_(attachment_ids),
                        Attachment.uploader_id == user.id,
                        Attachment.message_id.is_(None),
                    ).with_for_update()
                )
            ).all()
        )
        if len(attachments) != len(set(attachment_ids)):
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid attachment")
    now = datetime.now(UTC)
    expires_at = None
    disappearing = getattr(conversation, "disappearing_after_seconds", None)
    if disappearing:
        expires_at = now + timedelta(seconds=disappearing)
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
        client_message_id=client_message_id,
        reply_to_id=reply_to_id,
        text=None,
        text_ciphertext=encrypted_text.ciphertext if encrypted_text else None,
        text_nonce=encrypted_text.nonce if encrypted_text else None,
        text_key_id=encrypted_text.key_id if encrypted_text else None,
        encryption_version=encrypted_text.version if encrypted_text else None,
        created_at=now,
        updated_at=now,
        scheduled_at=scheduled_at,
        mentions=mentions_json,
        expires_at=expires_at,
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
    created = (
        await db.scalars(
            select(Message)
            .options(
                selectinload(Message.attachments),
                selectinload(Message.reads),
                selectinload(Message.reactions),
                selectinload(Message.reply_to),
            )
            .where(Message.id == message.id)
        )
    ).one()
    if normalized_text:
        try:
            from app.services.link_previews import schedule_preview_for_text

            schedule_preview_for_text(created.id, normalized_text)
        except Exception:
            logger.exception("Failed to schedule link preview")
    return created


async def create_message_idempotent(
    db: AsyncSession,
    user: User,
    conversation_id: str,
    client_message_id: str,
    text: str | None,
    attachment_ids: list[str] | None = None,
    reply_to_id: str | None = None,
    scheduled_at: datetime | None = None,
    mentions: list[str] | None = None,
) -> tuple[Message, bool]:
    query = (
        select(Message)
        .where(
            Message.sender_id == user.id,
            Message.conversation_id == conversation_id,
            Message.client_message_id == client_message_id,
        )
        .options(selectinload(Message.attachments), selectinload(Message.reads))
    )
    existing = (await db.scalars(query)).first()
    if existing is not None:
        return existing, False
    try:
        message = await create_message(
            db,
            user,
            conversation_id,
            text,
            attachment_ids,
            client_message_id=client_message_id,
            reply_to_id=reply_to_id,
            scheduled_at=scheduled_at,
            mentions=mentions,
        )
        return message, True
    except IntegrityError:
        await db.rollback()
        existing = (await db.scalars(query)).first()
        if existing is None:
            raise
        return existing, False


async def list_messages(
    db: AsyncSession,
    user_id: str,
    conversation_id: str,
    cursor: MessageCursor | None = None,
    limit: int = 30,
    message_type: str | None = None,
) -> tuple[list[Message], bool]:
    await require_participant(db, conversation_id, user_id)
    now = datetime.now(UTC)
    stmt = (
        select(Message)
        .options(selectinload(Message.attachments), selectinload(Message.reads))
        .where(Message.conversation_id == conversation_id, visible_messages_clause(now))
        .order_by(desc(Message.created_at), desc(Message.id))
        .limit(limit + 1)
    )
    if message_type is not None:
        mime_filter = _type_mime_filter(message_type)
        if mime_filter is not None:
            stmt = stmt.join(Attachment, Attachment.message_id == Message.id).where(mime_filter)
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
    return (
        await db.scalars(
            select(Message)
            .options(
                selectinload(Message.attachments),
                selectinload(Message.reads),
                selectinload(Message.reactions),
                selectinload(Message.reply_to),
            )
            .where(Message.id == message.id)
        )
    ).one()


async def edit_message(db: AsyncSession, message_id: str, user: User, new_text: str) -> Message:
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
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only sender can edit this message")
    if message.deleted_at is not None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Cannot edit a deleted message")
    if message.text_ciphertext is None and message.text is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Cannot edit an attachment-only message")
    now = datetime.now(UTC)
    encrypted_text = get_encryption_keyring().encrypt(
        new_text.encode("utf-8"),
        associated_data=message_text_associated_data(message.id),
    )
    message.text = None
    message.text_ciphertext = encrypted_text.ciphertext
    message.text_nonce = encrypted_text.nonce
    message.text_key_id = encrypted_text.key_id
    message.encryption_version = encrypted_text.version
    message.edited_at = now
    message.updated_at = now
    await db.commit()
    return (
        await db.scalars(
            select(Message)
            .options(
                selectinload(Message.attachments),
                selectinload(Message.reads),
                selectinload(Message.reactions),
                selectinload(Message.reply_to),
            )
            .where(Message.id == message.id)
        )
    ).one()


async def react_to_message(
    db: AsyncSession, message_id: str, user: User, emoji: str | None
) -> Message:
    message = (
        await db.scalars(
            select(Message)
            .options(
                selectinload(Message.attachments),
                selectinload(Message.reads),
                selectinload(Message.reactions),
                selectinload(Message.reply_to),
            )
            .where(Message.id == message_id)
        )
    ).first()
    if message is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Message not found")
    await require_participant(db, message.conversation_id, user.id)
    if message.deleted_at is not None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Cannot react to a deleted message")
    existing = (
        await db.scalars(
            select(MessageReaction).where(
                MessageReaction.message_id == message_id,
                MessageReaction.user_id == user.id,
            )
        )
    ).first()
    if not emoji:
        if existing is not None:
            await db.delete(existing)
            await db.commit()
    else:
        emoji = emoji[:16]
        if existing is not None:
            existing.emoji = emoji
        else:
            db.add(MessageReaction(message_id=message_id, user_id=user.id, emoji=emoji))
        await db.commit()
    db.expunge(message)
    return (
        await db.scalars(
            select(Message)
            .options(
                selectinload(Message.attachments),
                selectinload(Message.reads),
                selectinload(Message.reactions),
                selectinload(Message.reply_to),
            )
            .where(Message.id == message_id)
        )
    ).one()


async def validate_reply_target(db: AsyncSession, conversation_id: str, reply_to_id: str | None) -> None:
    if reply_to_id is None:
        return
    target = (await db.scalars(select(Message).where(Message.id == reply_to_id))).first()
    if (
        target is None
        or target.conversation_id != conversation_id
        or target.deleted_at is not None
    ):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid reply target")


async def search_user_messages(
    db: AsyncSession,
    user: User,
    query: str,
    limit: int = 20,
    per_conversation_scan: int = 500,
) -> list[dict]:
    from app.services.conversations import list_conversations

    needle = query.lower().strip()
    conversations = await list_conversations(db, user.id)
    matches: list[dict] = []
    now = datetime.now(UTC)
    for conversation in conversations:
        candidates = (
            await db.scalars(
                select(Message)
                .options(selectinload(Message.attachments), selectinload(Message.reads))
                .where(
                    Message.conversation_id == conversation.id,
                    Message.deleted_at.is_(None),
                    visible_messages_clause(now),
                )
                .order_by(desc(Message.created_at), desc(Message.id))
                .limit(per_conversation_scan)
            )
        ).all()
        for message in candidates:
            try:
                text = plaintext_message_text(message)
            except DecryptionError:
                continue
            if text and needle in text.lower():
                matches.append(message)
                if len(matches) >= limit:
                    return matches
    return matches


async def dispatch_due_messages_once(db=None) -> int:
    """Broadcast messages whose scheduled_at just became due."""
    from app.core.database import AsyncSessionLocal
    from app.core.redis import get_redis
    from app.services.conversations import require_participant
    from app.services.presence import is_online
    from app.services.push import schedule_message_push
    from app.websocket.events import conversation_participant_ids, serialize_message
    from app.websocket.manager import manager

    if db is None:
        async with AsyncSessionLocal() as session:
            return await dispatch_due_messages_once(session)
    now = datetime.now(UTC)
    due = list(
        (
            await db.scalars(
                select(Message)
                .options(
                    selectinload(Message.attachments),
                    selectinload(Message.reads),
                    selectinload(Message.reactions),
                    selectinload(Message.reply_to),
                )
                .where(
                    Message.scheduled_at.is_not(None),
                    Message.scheduled_at <= now,
                    Message.scheduled_notified_at.is_(None),
                    Message.deleted_at.is_(None),
                )
                .order_by(Message.scheduled_at)
                .limit(100)
            )
        ).all()
    )
    if not due:
        return 0
    count = 0
    redis = None
    for message in due:
        message.scheduled_notified_at = now
        count += 1
    await db.commit()
    for message in due:
        try:
            conversation = await require_participant(db, message.conversation_id, message.sender_id)
            refreshed = (
                await db.scalars(
                    select(Message)
                    .options(
                        selectinload(Message.attachments),
                        selectinload(Message.reads),
                        selectinload(Message.reactions),
                        selectinload(Message.reply_to),
                    )
                    .where(Message.id == message.id)
                )
            ).first()
            if refreshed is None:
                continue
            participants = await conversation_participant_ids(conversation)
            if redis is None:
                redis = await get_redis()
            payload = serialize_message(refreshed)
            await manager.broadcast_to_users(redis, participants, "message:new", payload)
            await manager.broadcast_to_users(
                redis,
                participants,
                "conversation:updated",
                {"conversation_id": refreshed.conversation_id, "latest_message": payload},
            )
            try:
                push_recipient_ids = [
                    pid
                    for pid in participants
                    if pid != refreshed.sender_id and not await is_online(redis, pid)
                ]
            except Exception:  # noqa: BLE001
                push_recipient_ids = [pid for pid in participants if pid != refreshed.sender_id]
            schedule_message_push(push_recipient_ids, refreshed.sender_id, refreshed.id)
        except Exception:
            logger.exception("Scheduled dispatch failed for message %s", message.id)
    return count


async def scheduled_dispatcher() -> None:
    while True:
        await asyncio.sleep(30)
        try:
            await dispatch_due_messages_once()
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Scheduled dispatcher cycle failed")


async def sweep_disappearing_messages(db=None) -> int:
    """Hard-delete expired messages and broadcast message:deleted (best effort)."""
    from app.core.database import AsyncSessionLocal
    from app.core.redis import get_redis
    from app.models.conversation import ConversationParticipant
    from app.websocket.manager import manager

    if db is None:
        async with AsyncSessionLocal() as session:
            return await sweep_disappearing_messages(session)
    now = datetime.now(UTC)
    expired = list(
        (
            await db.scalars(
                select(Message)
                .where(
                    Message.expires_at.is_not(None),
                    Message.expires_at <= now,
                )
                .order_by(Message.expires_at)
                .limit(500)
            )
        ).all()
    )
    if not expired:
        return 0
    # Capture participants before deleting rows.
    affected: list[tuple[str, str, list[str]]] = []
    for message in expired:
        participant_ids = list(
            (
                await db.scalars(
                    select(ConversationParticipant.user_id).where(
                        ConversationParticipant.conversation_id == message.conversation_id
                    )
                )
            ).all()
        )
        affected.append((message.id, message.conversation_id, participant_ids))
        await db.delete(message)
    await db.commit()
    redis = None
    for message_id, conversation_id, participant_ids in affected:
        try:
            if redis is None:
                redis = await get_redis()
            await manager.broadcast_to_users(
                redis,
                participant_ids,
                "message:deleted",
                {"message_id": message_id, "conversation_id": conversation_id},
            )
        except Exception:
            logger.exception("Disappearing broadcast failed for message %s", message_id)
    return len(affected)


async def disappearing_sweeper() -> None:
    while True:
        await asyncio.sleep(60)
        try:
            await sweep_disappearing_messages()
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Disappearing sweep failed")
