from datetime import UTC, datetime

from fastapi import HTTPException, status
from sqlalchemy import desc, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.conversation import Conversation, ConversationParticipant
from app.models.message import Message, MessageRead
from app.models.user import User


def private_key_for(user_a: str, user_b: str) -> str:
    return ":".join(sorted([user_a, user_b]))


async def require_participant(db: AsyncSession, conversation_id: str, user_id: str) -> Conversation:
    conversation = (
        await db.scalars(
            select(Conversation)
            .options(selectinload(Conversation.participants).selectinload(ConversationParticipant.user))
            .where(Conversation.id == conversation_id)
            .join(ConversationParticipant)
            .where(ConversationParticipant.user_id == user_id)
        )
    ).first()
    if conversation is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Conversation not found")
    return conversation


async def get_private_conversation_by_key(db: AsyncSession, private_key: str) -> Conversation | None:
    return (
        await db.scalars(
            select(Conversation)
            .options(selectinload(Conversation.participants).selectinload(ConversationParticipant.user))
            .where(Conversation.private_key == private_key)
        )
    ).first()


async def get_or_create_private_conversation(
    db: AsyncSession, current_user_id: str, participant_id: str
) -> Conversation:
    if current_user_id == participant_id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Cannot create conversation with yourself")
    other = await db.get(User, participant_id)
    if other is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")
    key = private_key_for(current_user_id, participant_id)
    conversation = await get_private_conversation_by_key(db, key)
    if conversation:
        return conversation
    conversation = Conversation(private_key=key)
    db.add(conversation)
    try:
        await db.flush()
        db.add_all(
            [
                ConversationParticipant(conversation_id=conversation.id, user_id=current_user_id),
                ConversationParticipant(conversation_id=conversation.id, user_id=participant_id),
            ]
        )
        await db.commit()
    except IntegrityError:
        await db.rollback()
        existing = await get_private_conversation_by_key(db, key)
        if existing is not None:
            return existing
        raise
    return await require_participant(db, conversation.id, current_user_id)


async def list_conversations(db: AsyncSession, user_id: str) -> list[Conversation]:
    stmt = (
        select(Conversation)
        .join(ConversationParticipant)
        .where(ConversationParticipant.user_id == user_id)
        .options(selectinload(Conversation.participants).selectinload(ConversationParticipant.user))
        .order_by(desc(Conversation.updated_at))
    )
    return list((await db.scalars(stmt)).unique().all())


async def latest_message(db: AsyncSession, conversation_id: str) -> Message | None:
    from sqlalchemy.orm import selectinload

    return (
        await db.scalars(
            select(Message)
            .options(selectinload(Message.attachments), selectinload(Message.reads))
            .where(Message.conversation_id == conversation_id)
            .order_by(desc(Message.created_at))
            .limit(1)
        )
    ).first()


async def unread_count(db: AsyncSession, conversation_id: str, user_id: str) -> int:
    participant = (
        await db.scalars(
            select(ConversationParticipant).where(
                ConversationParticipant.conversation_id == conversation_id,
                ConversationParticipant.user_id == user_id,
            )
        )
    ).first()
    last_read_at = participant.last_read_at if participant else None
    stmt = select(func.count(Message.id)).where(
        Message.conversation_id == conversation_id,
        Message.sender_id != user_id,
        Message.deleted_at.is_(None),
    )
    if last_read_at is not None:
        stmt = stmt.where(Message.created_at > last_read_at)
    return int(await db.scalar(stmt) or 0)


async def mark_conversation_read(db: AsyncSession, conversation_id: str, user_id: str) -> list[str]:
    await require_participant(db, conversation_id, user_id)
    now = datetime.now(UTC)
    participant = (
        await db.scalars(
            select(ConversationParticipant).where(
                ConversationParticipant.conversation_id == conversation_id,
                ConversationParticipant.user_id == user_id,
            )
        )
    ).one()
    participant.last_read_at = now
    unread_messages = (
        await db.scalars(
            select(Message).where(
                Message.conversation_id == conversation_id,
                Message.sender_id != user_id,
                Message.deleted_at.is_(None),
            )
        )
    ).all()
    message_ids: list[str] = []
    for message in unread_messages:
        exists = await db.scalar(
            select(MessageRead.id).where(MessageRead.message_id == message.id, MessageRead.user_id == user_id)
        )
        if not exists:
            db.add(MessageRead(message_id=message.id, user_id=user_id))
            message_ids.append(message.id)
    await db.commit()
    return message_ids
