"""Invite links / QR for group conversations."""

import secrets

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.conversation import Conversation, ConversationParticipant


def generate_invite_token() -> str:
    return secrets.token_urlsafe(24)


async def get_or_create_invite(db: AsyncSession, conversation: Conversation) -> str:
    if not conversation.invite_token:
        conversation.invite_token = generate_invite_token()
        await db.commit()
        await db.refresh(conversation)
    return conversation.invite_token


async def revoke_invite(db: AsyncSession, conversation: Conversation) -> str:
    conversation.invite_token = generate_invite_token()
    await db.commit()
    await db.refresh(conversation)
    return conversation.invite_token


async def find_conversation_by_token(
    db: AsyncSession, token: str
) -> Conversation | None:
    return (
        await db.scalars(
            select(Conversation)
            .options(selectinload(Conversation.participants).selectinload(ConversationParticipant.user))
            .where(Conversation.invite_token == token)
        )
    ).first()


async def join_via_invite(db: AsyncSession, token: str, user_id: str) -> Conversation:
    conversation = await find_conversation_by_token(db, token)
    if conversation is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Invalid invite link")
    if conversation.kind != "group":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Only group chats can be invited")
    if not any(p.user_id == user_id for p in conversation.participants):
        db.add(
            ConversationParticipant(conversation_id=conversation.id, user_id=user_id)
        )
        await db.commit()
        # expire_on_commit=False sessions keep the pre-join participants
        # collection; drop it so the refetch below sees the new member.
        db.expire(conversation, ["participants"])
    from app.services.conversations import require_participant

    return await require_participant(db, conversation.id, user_id)
