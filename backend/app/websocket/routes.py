import asyncio
import json
import logging
from contextlib import suppress
from datetime import UTC, datetime

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import get_ws_user_from_token
from app.core.database import AsyncSessionLocal
from app.core.redis import get_redis
from app.models.conversation import Conversation, ConversationParticipant
from app.models.user import User
from app.schemas.ws import (
    AuthPayload,
    ConversationIdPayload,
    MessageDeletePayload,
    MessageSendPayload,
    TypingPayload,
    WebSocketEnvelope,
)
from app.services.conversations import latest_message, mark_conversation_read, require_participant
from app.services.messages import create_message, delete_message_for_everyone
from app.services.presence import clear_typing, set_offline, set_online, set_typing
from app.services.push import schedule_message_push
from app.websocket.events import conversation_participant_ids, serialize_message
from app.websocket.manager import manager

router = APIRouter()
PRESENCE_HEARTBEAT_SECONDS = 15
logger = logging.getLogger(__name__)


async def participant_ids_for_user(db: AsyncSession, user_id: str) -> list[str]:
    conversations = (
        await db.scalars(
            select(Conversation)
            .join(ConversationParticipant)
            .where(ConversationParticipant.user_id == user_id)
            .options(selectinload(Conversation.participants))
        )
    ).unique().all()
    ids: set[str] = set()
    for conversation in conversations:
        ids.update(participant.user_id for participant in conversation.participants)
    return list(ids)


async def send_error(websocket: WebSocket, message: str, request_id: str | None = None) -> None:
    payload = {"detail": message}
    if request_id:
        payload["request_id"] = request_id
    await websocket.send_json({"type": "error", "payload": payload})


async def authenticate_websocket(db: AsyncSession, websocket: WebSocket) -> User:
    raw = await asyncio.wait_for(websocket.receive_json(), timeout=10)
    envelope = WebSocketEnvelope.model_validate(raw)
    if envelope.type != "auth":
        raise ValueError("First WebSocket event must be auth")
    payload = AuthPayload.model_validate(envelope.payload)
    return await get_ws_user_from_token(db, payload.token)


async def refresh_presence(redis, user_id: str, instance_id: str) -> None:
    try:
        while True:
            await asyncio.sleep(PRESENCE_HEARTBEAT_SECONDS)
            await set_online(redis, user_id, instance_id)
    except asyncio.CancelledError:
        raise


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket) -> None:
    await websocket.accept()
    redis = await get_redis()
    async with AsyncSessionLocal() as db:
        try:
            user = await authenticate_websocket(db, websocket)
        except (asyncio.TimeoutError, ValueError, ValidationError):
            await send_error(websocket, "Authentication required")
            await websocket.close(code=1008)
            return
        except Exception:
            logger.exception("Unexpected WebSocket authentication failure")
            await websocket.close(code=1008)
            return

        presence_task: asyncio.Task | None = None
        registered = False
        try:
            await manager.register(user.id, websocket)
            registered = True
            await websocket.send_json({"type": "auth:ok", "payload": {"user_id": user.id}})
            became_online = await set_online(redis, user.id, manager.instance_id)
            presence_task = asyncio.create_task(
                refresh_presence(redis, user.id, manager.instance_id)
            )
            if became_online:
                peer_ids = await participant_ids_for_user(db, user.id)
                await manager.broadcast_to_users(
                    redis, peer_ids, "user:online", {"user_id": user.id}
                )
            while True:
                try:
                    raw = await websocket.receive_json()
                except json.JSONDecodeError:
                    await send_error(websocket, "Invalid JSON payload")
                    continue
                except RuntimeError:
                    break
                request_id: str | None = None
                try:
                    envelope = WebSocketEnvelope.model_validate(raw)
                    request_id = envelope.request_id
                    await handle_event(db, redis, websocket, user, envelope)
                except ValidationError:
                    await db.rollback()
                    await send_error(websocket, "Invalid event payload", request_id)
                except Exception:
                    await db.rollback()
                    await send_error(websocket, "Unable to process event", request_id)
        except WebSocketDisconnect:
            pass
        finally:
            if presence_task is not None:
                presence_task.cancel()
                with suppress(asyncio.CancelledError):
                    await presence_task
            if registered:
                await manager.disconnect(user.id, websocket)
            if registered and not manager.is_connected(user.id):
                try:
                    still_online = await set_offline(redis, user.id, manager.instance_id)
                    if not still_online:
                        user.last_seen_at = datetime.now(UTC)
                        await db.commit()
                        peer_ids = await participant_ids_for_user(db, user.id)
                        await manager.broadcast_to_users(
                            redis,
                            peer_ids,
                            "user:offline",
                            {"user_id": user.id, "last_seen_at": user.last_seen_at.isoformat()},
                        )
                except Exception:
                    await db.rollback()
                    logger.exception("Failed to finalize disconnected WebSocket presence")


async def handle_event(db, redis, websocket: WebSocket, user: User, envelope: WebSocketEnvelope) -> None:
    if envelope.type == "conversation:join":
        payload = ConversationIdPayload.model_validate(envelope.payload)
        await require_participant(db, payload.conversation_id, user.id)
        await manager.join_room(payload.conversation_id, user.id)
        await websocket.send_json({"type": "conversation:joined", "payload": payload.model_dump()})
        return

    if envelope.type == "conversation:leave":
        payload = ConversationIdPayload.model_validate(envelope.payload)
        await manager.leave_room(payload.conversation_id, user.id)
        await websocket.send_json({"type": "conversation:left", "payload": payload.model_dump()})
        return

    if envelope.type == "typing:start":
        payload = TypingPayload.model_validate(envelope.payload)
        conversation = await require_participant(db, payload.conversation_id, user.id)
        await set_typing(redis, payload.conversation_id, user.id)
        await manager.broadcast_to_users(
            redis,
            await conversation_participant_ids(conversation),
            "typing:update",
            {"conversation_id": payload.conversation_id, "user_id": user.id, "is_typing": True},
        )
        return

    if envelope.type == "typing:stop":
        payload = TypingPayload.model_validate(envelope.payload)
        conversation = await require_participant(db, payload.conversation_id, user.id)
        await clear_typing(redis, payload.conversation_id, user.id)
        await manager.broadcast_to_users(
            redis,
            await conversation_participant_ids(conversation),
            "typing:update",
            {"conversation_id": payload.conversation_id, "user_id": user.id, "is_typing": False},
        )
        return

    if envelope.type == "message:send":
        payload = MessageSendPayload.model_validate(envelope.payload)
        message = await create_message(
            db, user, payload.conversation_id, payload.text, payload.attachment_ids
        )
        conversation = await require_participant(db, payload.conversation_id, user.id)
        participants = await conversation_participant_ids(conversation)
        message_payload = serialize_message(message)
        if envelope.request_id:
            message_payload["request_id"] = envelope.request_id
        await manager.broadcast_to_users(redis, participants, "message:new", message_payload)
        await manager.broadcast_to_users(
            redis,
            participants,
            "conversation:updated",
            {"conversation_id": payload.conversation_id, "latest_message": message_payload},
        )
        push_recipient_ids = [
            participant_id
            for participant_id in participants
            if participant_id != user.id
            and not manager.is_connected(participant_id)
            and not manager.is_in_room(payload.conversation_id, participant_id)
        ]
        schedule_message_push(push_recipient_ids, user.id, message.id)
        return

    if envelope.type == "message:delete":
        payload = MessageDeletePayload.model_validate(envelope.payload)
        message = await delete_message_for_everyone(db, payload.message_id, user)
        conversation = await require_participant(db, message.conversation_id, user.id)
        participants = await conversation_participant_ids(conversation)
        await manager.broadcast_to_users(redis, participants, "message:deleted", serialize_message(message))
        latest = await latest_message(db, message.conversation_id)
        if latest is not None:
            await manager.broadcast_to_users(
                redis,
                participants,
                "conversation:updated",
                {"conversation_id": message.conversation_id, "latest_message": serialize_message(latest)},
            )
        return

    if envelope.type == "message:read":
        payload = ConversationIdPayload.model_validate(envelope.payload)
        message_ids = await mark_conversation_read(db, payload.conversation_id, user.id)
        conversation = await require_participant(db, payload.conversation_id, user.id)
        await manager.broadcast_to_users(
            redis,
            await conversation_participant_ids(conversation),
            "message:read",
            {
                "conversation_id": payload.conversation_id,
                "user_id": user.id,
                "message_ids": message_ids,
                "read_at": datetime.now(UTC).isoformat(),
            },
        )
        return

    await send_error(websocket, "Unknown event type", envelope.request_id)
