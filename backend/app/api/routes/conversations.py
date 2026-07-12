from datetime import UTC, datetime

from fastapi import APIRouter, Query

from app.api.deps import CurrentUser, DbSession
from app.core.redis import get_redis
from app.schemas.conversation import ConversationCreate, ConversationDetail, ConversationOut
from app.schemas.message import MessageHistory
from app.schemas.user import UserSearchResult
from app.services.conversations import (
    get_or_create_private_conversation,
    latest_messages,
    list_conversations,
    mark_conversation_read,
    require_participant,
    unread_counts,
)
from app.services.messages import decode_message_cursor, encode_message_cursor, list_messages
from app.services.presence import online_map
from app.websocket.events import serialize_message
from app.websocket.events import conversation_participant_ids
from app.websocket.manager import manager

router = APIRouter(prefix="/conversations", tags=["conversations"])


async def serialize_conversations(
    db: DbSession, conversations: list, current_user_id: str
) -> list[ConversationOut]:
    if not conversations:
        return []
    redis = await get_redis()
    conversation_ids = [conversation.id for conversation in conversations]
    users_by_id = {
        participant.user.id: participant.user
        for conversation in conversations
        for participant in conversation.participants
    }
    online = await online_map(redis, list(users_by_id))
    latest_by_conversation = await latest_messages(db, conversation_ids)
    unread_by_conversation = await unread_counts(db, conversation_ids, current_user_id)
    serialized: list[ConversationOut] = []
    for conversation in conversations:
        participants = [participant.user for participant in conversation.participants]
        latest = latest_by_conversation.get(conversation.id)
        serialized.append(
            ConversationOut(
                id=conversation.id,
                kind=conversation.kind,
                participants=[
                    UserSearchResult(
                        id=user.id,
                        username=user.username,
                        display_name=user.display_name,
                        avatar_url=user.avatar_url,
                        last_seen_at=user.last_seen_at,
                        is_online=online.get(user.id, False),
                    )
                    for user in participants
                ],
                latest_message=serialize_message(latest) if latest else None,
                unread_count=unread_by_conversation[conversation.id],
                created_at=conversation.created_at,
                updated_at=conversation.updated_at,
            )
        )
    return serialized


async def serialize_conversation(db: DbSession, conversation, current_user_id: str) -> ConversationOut:
    return (await serialize_conversations(db, [conversation], current_user_id))[0]


@router.get("", response_model=list[ConversationOut])
async def conversations(current_user: CurrentUser, db: DbSession) -> list[ConversationOut]:
    rows = await list_conversations(db, current_user.id)
    return await serialize_conversations(db, rows, current_user.id)


@router.post("", response_model=ConversationDetail)
async def create_conversation(
    payload: ConversationCreate, current_user: CurrentUser, db: DbSession
) -> ConversationDetail:
    conversation = await get_or_create_private_conversation(db, current_user.id, payload.participant_id)
    serialized = await serialize_conversation(db, conversation, current_user.id)
    return ConversationDetail.model_validate(serialized.model_dump())


@router.get("/{conversation_id}", response_model=ConversationDetail)
async def get_conversation(
    conversation_id: str, current_user: CurrentUser, db: DbSession
) -> ConversationDetail:
    conversation = await require_participant(db, conversation_id, current_user.id)
    serialized = await serialize_conversation(db, conversation, current_user.id)
    return ConversationDetail.model_validate(serialized.model_dump())


@router.get("/{conversation_id}/messages", response_model=MessageHistory)
async def get_messages(
    conversation_id: str,
    current_user: CurrentUser,
    db: DbSession,
    cursor: str | None = Query(default=None, max_length=512),
    limit: int = Query(default=30, ge=1, le=100),
) -> MessageHistory:
    decoded_cursor = decode_message_cursor(cursor) if cursor else None
    rows, has_more = await list_messages(
        db, current_user.id, conversation_id, decoded_cursor, limit
    )
    items = [serialize_message(row) for row in rows]
    return MessageHistory(
        items=items,
        has_more=has_more,
        next_cursor=encode_message_cursor(rows[-1]) if has_more and rows else None,
    )


@router.post("/{conversation_id}/read", response_model=dict)
async def read_conversation(conversation_id: str, current_user: CurrentUser, db: DbSession) -> dict:
    message_ids = await mark_conversation_read(db, conversation_id, current_user.id)
    conversation = await require_participant(db, conversation_id, current_user.id)
    redis = await get_redis()
    read_at = datetime.now(UTC)
    await manager.broadcast_to_users(
        redis,
        await conversation_participant_ids(conversation),
        "message:read",
        {
            "conversation_id": conversation_id,
            "user_id": current_user.id,
            "message_ids": message_ids,
            "read_at": read_at.isoformat(),
        },
    )
    return {"message_ids": message_ids}
