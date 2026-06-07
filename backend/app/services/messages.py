from datetime import UTC, datetime

from fastapi import HTTPException, status
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.attachment import Attachment
from app.models.message import Message
from app.models.user import User
from app.services.conversations import require_participant


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
    message = Message(
        conversation_id=conversation_id,
        sender_id=user.id,
        text=text.strip() if text else None,
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
    cursor: datetime | None = None,
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
        stmt = stmt.where(Message.created_at < cursor)
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
    await db.commit()
    await db.refresh(message, attribute_names=["attachments", "reads"])
    return message
