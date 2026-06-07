from fastapi import APIRouter

from app.api.deps import CurrentUser, DbSession
from app.core.redis import get_redis
from app.schemas.message import MessageOut
from app.services.conversations import latest_message, require_participant
from app.services.messages import delete_message_for_everyone
from app.websocket.events import conversation_participant_ids, serialize_message
from app.websocket.manager import manager

router = APIRouter(prefix="/messages", tags=["messages"])


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
