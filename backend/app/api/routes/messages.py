from fastapi import APIRouter, Response, status

from app.api.deps import CurrentUser, DbSession
from app.core.redis import get_redis
from app.schemas.message import MessageCreate, MessageOut
from app.services.conversations import latest_message, require_participant
from app.services.messages import create_message_idempotent, delete_message_for_everyone
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
    message, created = await create_message_idempotent(
        db,
        current_user,
        payload.conversation_id,
        payload.client_message_id,
        payload.text,
        payload.attachment_ids,
    )
    message_payload = serialize_message(message)
    if not created:
        response.status_code = status.HTTP_200_OK
        return message_payload

    conversation = await require_participant(db, message.conversation_id, current_user.id)
    participants = await conversation_participant_ids(conversation)
    redis = await get_redis()
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
        and not manager.is_connected(participant_id)
        and not manager.is_in_room(message.conversation_id, participant_id)
    ]
    schedule_message_push(push_recipient_ids, current_user.id, message.id)
    return message_payload


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
