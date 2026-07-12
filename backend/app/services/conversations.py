from datetime import UTC, datetime

from fastapi import HTTPException, status
from sqlalchemy import and_, desc, func, or_, select
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
            .order_by(desc(Message.created_at), desc(Message.id))
            .limit(1)
        )
    ).first()


async def latest_messages(
    db: AsyncSession, conversation_ids: list[str]
) -> dict[str, Message]:
    if not conversation_ids:
        return {}
    ranked = (
        select(
            Message.id.label("message_id"),
            func.row_number()
            .over(
                partition_by=Message.conversation_id,
                order_by=(desc(Message.created_at), desc(Message.id)),
            )
            .label("position"),
        )
        .where(Message.conversation_id.in_(conversation_ids))
        .subquery()
    )
    rows = (
        await db.scalars(
            select(Message)
            .join(ranked, ranked.c.message_id == Message.id)
            .where(ranked.c.position == 1)
            .options(selectinload(Message.attachments), selectinload(Message.reads))
        )
    ).unique().all()
    return {message.conversation_id: message for message in rows}


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


async def unread_counts(
    db: AsyncSession, conversation_ids: list[str], user_id: str
) -> dict[str, int]:
    if not conversation_ids:
        return {}
    rows = await db.execute(
        select(Message.conversation_id, func.count(Message.id))
        .join(
            ConversationParticipant,
            and_(
                ConversationParticipant.conversation_id == Message.conversation_id,
                ConversationParticipant.user_id == user_id,
            ),
        )
        .where(
            Message.conversation_id.in_(conversation_ids),
            Message.sender_id != user_id,
            Message.deleted_at.is_(None),
            or_(
                ConversationParticipant.last_read_at.is_(None),
                Message.created_at > ConversationParticipant.last_read_at,
            ),
        )
        .group_by(Message.conversation_id)
    )
    counts = {conversation_id: int(count) for conversation_id, count in rows.all()}
    return {conversation_id: counts.get(conversation_id, 0) for conversation_id in conversation_ids}


async def mark_conversation_read(db: AsyncSession, conversation_id: str, user_id: str) -> list[str]:
    await require_participant(db, conversation_id, user_id)
    now = datetime.now(UTC)
    participant = (
        await db.scalars(
            select(ConversationParticipant)
            .where(
                ConversationParticipant.conversation_id == conversation_id,
                ConversationParticipant.user_id == user_id,
            )
            .with_for_update()
        )
    ).one()
    previous_last_read_at = participant.last_read_at
    participant.last_read_at = now
    unread_query = select(Message.id).where(
        Message.conversation_id == conversation_id,
        Message.sender_id != user_id,
        Message.deleted_at.is_(None),
        Message.created_at <= now,
    )
    if previous_last_read_at is not None:
        unread_query = unread_query.where(Message.created_at > previous_last_read_at)
    candidate_ids = list((await db.scalars(unread_query)).all())

    existing_ids: set[str] = set()
    if candidate_ids:
        existing_ids = set(
            (
                await db.scalars(
                    select(MessageRead.message_id).where(
                        MessageRead.user_id == user_id,
                        MessageRead.message_id.in_(candidate_ids),
                    )
                )
            ).all()
        )
    message_ids = [message_id for message_id in candidate_ids if message_id not in existing_ids]
    db.add_all(
        [MessageRead(message_id=message_id, user_id=user_id) for message_id in message_ids]
    )
    await db.commit()
    return message_ids
