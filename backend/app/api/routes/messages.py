from fastapi import APIRouter, HTTPException, Response, status

from app.api.deps import CurrentUser, DbSession, DeviceId
from app.core.rate_limit import consume_message_allowance
from app.core.redis import get_redis
from app.schemas.message import MessageCreate, MessageEdit, MessageOut
from app.services.conversations import latest_message, require_participant
from app.services.e2ee_messages import create_e2ee_message, device_envelope, envelopes_by_user
from app.services.messages import (
    create_message_idempotent,
    delete_message_for_everyone,
    edit_message,
    is_scheduled_pending,
    react_to_message,
)
from app.services.presence import is_online
from app.services.push import schedule_message_push
from app.websocket.events import conversation_participant_ids, serialize_message
from app.websocket.manager import manager

router = APIRouter(prefix="/messages", tags=["messages"])


@router.post("", response_model=MessageOut, status_code=status.HTTP_201_CREATED)
async def send_message(
    payload: MessageCreate,
    response: Response,
    current_user: CurrentUser,
    db: DbSession,
) -> dict:
    if not await consume_message_allowance(current_user.id):
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Too many messages")
    if payload.envelopes is not None:
        message, created = await create_e2ee_message(db, current_user, payload)
    else:
        message, created = await create_message_idempotent(
            db,
            current_user,
            payload.conversation_id,
            payload.client_message_id,
            payload.text,
            payload.attachment_ids,
            reply_to_id=payload.reply_to_id,
            scheduled_at=payload.scheduled_at,
            mentions=payload.mentions,
        )
    message_payload = serialize_message(message)
    if not created:
        response.status_code = status.HTTP_200_OK
        return message_payload
    if is_scheduled_pending(message):
        return message_payload

    conversation = await require_participant(db, message.conversation_id, current_user.id)
    participants = await conversation_participant_ids(conversation)
    redis = await get_redis()
    if message.e2ee:
        # Each user's sockets receive only the envelopes addressed to their devices.
        envelopes = await envelopes_by_user(db, message.id)
        for participant_id in participants:
            await manager.broadcast_to_users(
                redis,
                [participant_id],
                "message:new",
                {**message_payload, "envelopes": envelopes.get(participant_id, {})},
            )
    else:
        await manager.broadcast_to_users(redis, participants, "message:new", message_payload)
    await manager.broadcast_to_users(
        redis,
        participants,
        "conversation:updated",
        {"conversation_id": message.conversation_id, "latest_message": message_payload},
    )
    push_recipient_ids = [
        participant_id
        for participant_id in participants
        if participant_id != current_user.id
        and not await is_online(redis, participant_id)
    ]
    schedule_message_push(push_recipient_ids, current_user.id, message.id)
    return message_payload


@router.patch("/{message_id}", response_model=MessageOut)
async def edit_message_endpoint(
    message_id: str,
    payload: MessageEdit,
    current_user: CurrentUser,
    db: DbSession,
) -> dict:
    message = await edit_message(db, message_id, current_user, payload.text)
    conversation = await require_participant(db, message.conversation_id, current_user.id)
    participants = await conversation_participant_ids(conversation)
    redis = await get_redis()
    message_payload = serialize_message(message)
    await manager.broadcast_to_users(redis, participants, "message:edited", message_payload)
    latest = await latest_message(db, message.conversation_id)
    if latest is not None:
        await manager.broadcast_to_users(
            redis,
            participants,
            "conversation:updated",
            {"conversation_id": message.conversation_id, "latest_message": serialize_message(latest)},
        )
    return message_payload


@router.put("/{message_id}/react", response_model=MessageOut)
async def react_message(
    message_id: str, payload: dict, current_user: CurrentUser, db: DbSession
) -> dict:
    from app.schemas.ws import MessageReactPayload

    try:
        parsed = MessageReactPayload.model_validate({"message_id": message_id, **payload})
    except Exception as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Invalid reaction") from exc
    message = await react_to_message(db, message_id, current_user, parsed.emoji)
    conversation = await require_participant(db, message.conversation_id, current_user.id)
    participants = await conversation_participant_ids(conversation)
    redis = await get_redis()
    await manager.broadcast_to_users(
        redis, participants, "message:updated", serialize_message(message)
    )
    return serialize_message(message)


@router.delete("/{message_id}", response_model=MessageOut)
async def delete_message(message_id: str, current_user: CurrentUser, db: DbSession) -> dict:
    message = await delete_message_for_everyone(db, message_id, current_user)
    conversation = await require_participant(db, message.conversation_id, current_user.id)
    participants = await conversation_participant_ids(conversation)
    redis = await get_redis()
    message_payload = serialize_message(message)
    await manager.broadcast_to_users(redis, participants, "message:deleted", message_payload)
    latest = await latest_message(db, message.conversation_id)
    if latest is not None:
        await manager.broadcast_to_users(
            redis,
            participants,
            "conversation:updated",
            {"conversation_id": message.conversation_id, "latest_message": serialize_message(latest)},
        )
    return message_payload


@router.get("/{message_id}/envelope", response_model=dict)
async def get_envelope(
    message_id: str, current_user: CurrentUser, db: DbSession, device_id: DeviceId
) -> dict:
    """This device's envelope for an E2EE message (fallback when a live event lacked it)."""
    from app.models.message import Message

    message = await db.get(Message, message_id)
    if message is None or not message.e2ee or not device_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Envelope not found")
    await require_participant(db, message.conversation_id, current_user.id)
    envelope = await device_envelope(db, message, current_user.id, device_id)
    if envelope is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Envelope not found")
    return {"message_id": message_id, "envelope": envelope}
