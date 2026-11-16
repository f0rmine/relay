"""Storage and delivery of end-to-end encrypted messages (Phase 2b).

The server never sees content: it stores one opaque envelope per recipient
device and hands each device only its own envelope.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from fastapi import HTTPException, status
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.conversation import Conversation
from app.models.e2ee import E2eeDevice, E2eeIdentity, MessageEnvelope
from app.models.message import Message
from app.models.user import User
from app.schemas.message import MessageCreate
from app.services.conversations import require_participant

DeviceKey = tuple[str, str]  # (user_id, device_id)


def _message_query(message_id: str):
    return (
        select(Message)
        .options(
            selectinload(Message.attachments),
            selectinload(Message.reads),
            selectinload(Message.reactions),
            selectinload(Message.reply_to),
        )
        .where(Message.id == message_id)
    )


async def active_devices(db: AsyncSession, user_ids: list[str]) -> set[DeviceKey]:
    rows = (
        await db.execute(
            select(E2eeDevice.user_id, E2eeDevice.device_id).where(
                E2eeDevice.user_id.in_(user_ids), E2eeDevice.revoked_at.is_(None)
            )
        )
    ).all()
    return {(user_id, device_id) for user_id, device_id in rows}


async def users_ready_for_e2ee(db: AsyncSession, user_ids: list[str]) -> bool:
    """Every user has an identity key and at least one active device."""
    identities = set(
        (
            await db.scalars(select(E2eeIdentity.user_id).where(E2eeIdentity.user_id.in_(user_ids)))
        ).all()
    )
    with_devices = {user_id for user_id, _ in await active_devices(db, user_ids)}
    return all(user_id in identities and user_id in with_devices for user_id in user_ids)


def _device_list(keys: set[DeviceKey]) -> list[dict[str, str]]:
    return [{"user_id": user, "device_id": device} for user, device in sorted(keys)]


async def create_e2ee_message(
    db: AsyncSession, user: User, payload: MessageCreate
) -> tuple[Message, bool]:
    from app.services.messages import validate_reply_target

    existing_query = select(Message.id).where(
        Message.sender_id == user.id,
        Message.conversation_id == payload.conversation_id,
        Message.client_message_id == payload.client_message_id,
    )
    existing_id = await db.scalar(existing_query)
    if existing_id is not None:
        return (await db.scalars(_message_query(existing_id))).one(), False

    conversation = await require_participant(db, payload.conversation_id, user.id)
    if not conversation.e2ee:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Conversation is not end-to-end encrypted")
    participant_ids = [participant.user_id for participant in conversation.participants]
    if conversation.kind == "private":
        from app.services.blocks import is_blocked

        for other_id in participant_ids:
            if other_id != user.id and await is_blocked(db, user.id, other_id):
                raise HTTPException(status.HTTP_404_NOT_FOUND, "Conversation not found")

    sender_device = await db.scalar(
        select(E2eeDevice).where(
            E2eeDevice.user_id == user.id,
            E2eeDevice.device_id == payload.sender_device_id,
            E2eeDevice.revoked_at.is_(None),
        )
    )
    if sender_device is None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Unknown sending device")

    envelopes = payload.envelopes or []
    given = [(envelope.user_id, envelope.device_id) for envelope in envelopes]
    if len(given) != len(set(given)):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Duplicate envelope recipients")
    expected = await active_devices(db, participant_ids)
    expected.discard((user.id, sender_device.device_id))
    missing = expected - set(given)
    extra = set(given) - expected
    if missing or extra:
        # The client refreshes its view of the directory and re-encrypts.
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            {
                "code": "device_mismatch",
                "missing": _device_list(missing),
                "extra": _device_list(extra),
            },
        )

    await validate_reply_target(db, conversation.id, payload.reply_to_id)
    now = datetime.now(UTC)
    disappearing = conversation.disappearing_after_seconds
    message = Message(
        id=str(uuid4()),
        conversation_id=conversation.id,
        sender_id=user.id,
        client_message_id=payload.client_message_id,
        text=None,
        e2ee=True,
        sender_device_id=sender_device.device_id,
        reply_to_id=payload.reply_to_id,
        scheduled_at=payload.scheduled_at,
        expires_at=now + timedelta(seconds=disappearing) if disappearing else None,
    )
    db.add(message)
    # No ORM relationship links envelopes to messages, so make the insert order
    # explicit; Postgres enforces the FK (SQLite in tests does not).
    try:
        await db.flush()
    except IntegrityError:
        await db.rollback()
        existing_id = await db.scalar(existing_query)
        if existing_id is None:
            raise
        return (await db.scalars(_message_query(existing_id))).one(), False
    db.add_all(
        MessageEnvelope(
            message_id=message.id,
            recipient_user_id=envelope.user_id,
            recipient_device_id=envelope.device_id,
            ciphertext=envelope.ciphertext,
        )
        for envelope in envelopes
    )
    touched = await db.get(Conversation, conversation.id)
    if touched is not None:
        touched.updated_at = now
    sender_device.last_seen_at = now
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        existing_id = await db.scalar(existing_query)
        if existing_id is None:
            raise
        return (await db.scalars(_message_query(existing_id))).one(), False
    return (await db.scalars(_message_query(message.id))).one(), True


async def envelopes_by_user(db: AsyncSession, message_id: str) -> dict[str, dict[str, str]]:
    """{user_id: {device_id: ciphertext}} for live per-user delivery."""
    rows = (
        await db.scalars(select(MessageEnvelope).where(MessageEnvelope.message_id == message_id))
    ).all()
    grouped: dict[str, dict[str, str]] = defaultdict(dict)
    for row in rows:
        grouped[row.recipient_user_id][row.recipient_device_id] = row.ciphertext
    return grouped


async def attach_device_envelopes(
    db: AsyncSession, payloads: list[dict], user_id: str, device_id: str | None
) -> list[dict]:
    """Fill `envelope` on serialized E2EE messages for the requesting device only."""
    ids = [payload["id"] for payload in payloads if payload.get("e2ee")]
    if not ids or not device_id:
        return payloads
    rows = (
        await db.scalars(
            select(MessageEnvelope).where(
                MessageEnvelope.message_id.in_(ids),
                MessageEnvelope.recipient_user_id == user_id,
                MessageEnvelope.recipient_device_id == device_id,
            )
        )
    ).all()
    by_message = {row.message_id: row.ciphertext for row in rows}
    for payload in payloads:
        if payload.get("e2ee"):
            payload["envelope"] = by_message.get(payload["id"])
    return payloads


async def device_envelope(
    db: AsyncSession, message: Message, user_id: str, device_id: str
) -> str | None:
    return await db.scalar(
        select(MessageEnvelope.ciphertext).where(
            MessageEnvelope.message_id == message.id,
            MessageEnvelope.recipient_user_id == user_id,
            MessageEnvelope.recipient_device_id == device_id,
        )
    )


async def delete_envelopes(db: AsyncSession, message_id: str) -> None:
    await db.execute(delete(MessageEnvelope).where(MessageEnvelope.message_id == message_id))
