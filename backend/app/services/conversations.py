from contextlib import suppress
from datetime import UTC, datetime
from uuid import uuid4

from fastapi import HTTPException, UploadFile, status
from sqlalchemy import and_, asc, desc, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.conversation import Conversation, ConversationParticipant
from app.models.message import Message, MessageRead
from app.models.user import User
from app.services.users import remove_previous_avatar_file, store_avatar_file, validate_image_upload


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
            .options(selectinload(Message.attachments), selectinload(Message.reads), selectinload(Message.reactions), selectinload(Message.reply_to))
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
            .options(selectinload(Message.attachments), selectinload(Message.reads), selectinload(Message.reactions), selectinload(Message.reply_to))
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


async def first_unread_message_id(
    db: AsyncSession, conversation_id: str, user_id: str
) -> str | None:
    return (await first_unread_ids(db, [conversation_id], user_id)).get(conversation_id)


async def first_unread_ids(
    db: AsyncSession, conversation_ids: list[str], user_id: str
) -> dict[str, str | None]:
    if not conversation_ids:
        return {}
    ranked = (
        select(
            Message.id.label("message_id"),
            Message.conversation_id.label("conversation_id"),
            func.row_number()
            .over(
                partition_by=Message.conversation_id,
                order_by=(asc(Message.created_at), asc(Message.id)),
            )
            .label("position"),
        )
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
        .subquery()
    )
    rows = await db.execute(
        select(ranked.c.conversation_id, ranked.c.message_id).where(ranked.c.position == 1)
    )
    found = {str(cid): str(mid) for cid, mid in rows.all()}
    return {conversation_id: found.get(conversation_id) for conversation_id in conversation_ids}


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


async def create_group_conversation(
    db: AsyncSession, creator_id: str, title: str, participant_ids: list[str]
) -> Conversation:
    unique_ids = [pid for pid in dict.fromkeys(participant_ids) if pid != creator_id]
    if len(unique_ids) < 2:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Group needs at least two other participants")
    found = (await db.scalars(select(User).where(User.id.in_(unique_ids)))).all()
    if len(found) != len(unique_ids):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")
    conversation = Conversation(kind="group", title=title.strip()[:120] or None, private_key=f"group:{uuid4()}")
    db.add(conversation)
    await db.flush()
    db.add(ConversationParticipant(conversation_id=conversation.id, user_id=creator_id, is_admin=True))
    for user_id in unique_ids:
        db.add(ConversationParticipant(conversation_id=conversation.id, user_id=user_id))
    await db.commit()
    return await require_participant(db, conversation.id, creator_id)


def participant_for(conversation: Conversation, user_id: str) -> ConversationParticipant:
    for participant in conversation.participants:
        if participant.user_id == user_id:
            return participant
    raise HTTPException(status.HTTP_404_NOT_FOUND, "Conversation not found")


async def require_group_admin(db: AsyncSession, conversation_id: str, user_id: str) -> Conversation:
    conversation = await require_participant(db, conversation_id, user_id)
    if conversation.kind != "group":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Not a group conversation")
    if not participant_for(conversation, user_id).is_admin:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only group admins can do this")
    return conversation


async def rename_group(db: AsyncSession, conversation: Conversation, title: str) -> Conversation:
    conversation.title = title.strip()[:120] or None
    conversation.updated_at = datetime.now(UTC)
    await db.commit()
    return conversation


async def save_group_avatar(db: AsyncSession, conversation: Conversation, file: UploadFile) -> Conversation:
    data, _content_type, suffix = await validate_image_upload(file)
    path, new_url = await store_avatar_file(data, suffix)
    previous_avatar_url = conversation.avatar_url
    conversation.avatar_url = new_url
    conversation.updated_at = datetime.now(UTC)
    try:
        await db.commit()
    except Exception:
        await db.rollback()
        with suppress(FileNotFoundError):
            path.unlink()
        raise
    remove_previous_avatar_file(previous_avatar_url, keep_path=path)
    await db.refresh(conversation)
    return conversation


async def add_group_participants(
    db: AsyncSession, conversation: Conversation, participant_ids: list[str]
) -> list[str]:
    existing = {participant.user_id for participant in conversation.participants}
    wanted = [pid for pid in dict.fromkeys(participant_ids) if pid not in existing]
    added: list[str] = []
    for user_id in wanted:
        if await db.get(User, user_id) is None:
            continue
        db.add(ConversationParticipant(conversation_id=conversation.id, user_id=user_id))
        added.append(user_id)
    if added:
        conversation.updated_at = datetime.now(UTC)
        await db.commit()
    return added


async def remove_group_participant(
    db: AsyncSession, conversation: Conversation, target_user_id: str
) -> None:
    participant = next(
        (p for p in conversation.participants if p.user_id == target_user_id), None
    )
    if participant is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")
    await db.delete(participant)
    await db.commit()


async def leave_conversation(db: AsyncSession, conversation_id: str, user_id: str) -> str:
    conversation = await require_participant(db, conversation_id, user_id)
    me = participant_for(conversation, user_id)
    remaining = [p for p in conversation.participants if p.user_id != user_id]
    await db.delete(me)
    await db.commit()
    if not remaining:
        await db.delete(conversation)
        await db.commit()
        return "deleted"
    if conversation.kind == "group" and me.is_admin:
        successor = min(remaining, key=lambda p: p.joined_at)
        successor.is_admin = True
        await db.commit()
    return "left"


async def set_pinned_message(
    db: AsyncSession, conversation: Conversation, message_id: str | None
) -> None:
    if message_id is not None:
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
        if (
            message is None
            or message.conversation_id != conversation.id
            or message.deleted_at is not None
        ):
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Cannot pin this message")
    conversation.pinned_message_id = message_id
    await db.commit()
