import asyncio
import json
import logging
from collections import defaultdict
from contextlib import suppress
from uuid import uuid4

from fastapi import WebSocket, WebSocketDisconnect
from redis.asyncio import Redis

logger = logging.getLogger(__name__)


class ConnectionManager:
    def __init__(self) -> None:
        self.instance_id = str(uuid4())
        self.user_connections: dict[str, set[WebSocket]] = defaultdict(set)
        self.rooms: dict[str, dict[str, int]] = defaultdict(dict)
        self._ws_rooms: dict[WebSocket, set[str]] = {}
        self._lock = asyncio.Lock()

    async def connect(self, user_id: str, websocket: WebSocket) -> None:
        await websocket.accept()
        await self.register(user_id, websocket)

    async def register(self, user_id: str, websocket: WebSocket) -> None:
        async with self._lock:
            self.user_connections[user_id].add(websocket)

    async def disconnect(self, user_id: str, websocket: WebSocket) -> None:
        async with self._lock:
            connections = self.user_connections.get(user_id)
            if connections:
                connections.discard(websocket)
                if not connections:
                    self.user_connections.pop(user_id, None)
            for conversation_id in self._ws_rooms.pop(websocket, set()):
                members = self.rooms.get(conversation_id)
                if members is None:
                    continue
                remaining = members.get(user_id, 0) - 1
                if remaining > 0:
                    members[user_id] = remaining
                else:
                    members.pop(user_id, None)
                if not members:
                    self.rooms.pop(conversation_id, None)

    async def join_room(self, conversation_id: str, user_id: str, websocket: WebSocket) -> None:
        async with self._lock:
            members = self.rooms[conversation_id]
            members[user_id] = members.get(user_id, 0) + 1
            self._ws_rooms.setdefault(websocket, set()).add(conversation_id)

    async def leave_room(self, conversation_id: str, user_id: str, websocket: WebSocket) -> None:
        async with self._lock:
            joined = self._ws_rooms.get(websocket)
            if joined is not None:
                joined.discard(conversation_id)
            members = self.rooms.get(conversation_id)
            if members is None:
                return
            remaining = members.get(user_id, 0) - 1
            if remaining > 0:
                members[user_id] = remaining
            else:
                members.pop(user_id, None)
            if not members:
                self.rooms.pop(conversation_id, None)

    def is_connected(self, user_id: str) -> bool:
        return bool(self.user_connections.get(user_id))

    def is_in_room(self, conversation_id: str, user_id: str) -> bool:
        return bool(self.rooms.get(conversation_id, {}).get(user_id))

    async def send_to_user(self, user_id: str, event: dict) -> None:
        connections = list(self.user_connections.get(user_id, set()))
        stale: list[WebSocket] = []
        for websocket in connections:
            try:
                await websocket.send_json(event)
            except (RuntimeError, WebSocketDisconnect):
                stale.append(websocket)
            except Exception:
                logger.exception("Removing WebSocket that failed during event delivery")
                stale.append(websocket)
        if stale:
            async with self._lock:
                for websocket in stale:
                    remaining = self.user_connections.get(user_id)
                    if remaining is None:
                        continue
                    remaining.discard(websocket)
                    if not remaining:
                        self.user_connections.pop(user_id, None)

    async def broadcast_to_users(
        self, redis: Redis, user_ids: list[str], event_type: str, payload: dict
    ) -> None:
        event = {"type": event_type, "payload": payload}
        for user_id in set(user_ids):
            await self.send_to_user(user_id, event)
        try:
            await redis.publish(
                "pubsub:broadcast",
                json.dumps(
                    {
                        "origin": self.instance_id,
                        "user_ids": list(set(user_ids)),
                        "event": event,
                    },
                    default=str,
                ),
            )
        except Exception:
            # The business operation may already be committed and delivered locally.
            logger.exception("Redis realtime fanout failed")

    async def redis_subscriber(self, redis: Redis) -> None:
        while True:
            pubsub = redis.pubsub()
            try:
                await pubsub.subscribe("pubsub:broadcast")
                async for message in pubsub.listen():
                    if message.get("type") != "message":
                        continue
                    try:
                        data = json.loads(message["data"])
                    except (json.JSONDecodeError, TypeError):
                        continue
                    if not isinstance(data, dict):
                        continue
                    if data.get("origin") == self.instance_id:
                        continue
                    event = data.get("event")
                    user_ids = data.get("user_ids")
                    if not isinstance(event, dict) or not isinstance(user_ids, list):
                        continue
                    for user_id in user_ids:
                        if isinstance(user_id, str):
                            await self.send_to_user(user_id, event)
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Redis Pub/Sub subscriber lost connection; retrying in 1s")
                await asyncio.sleep(1)
            finally:
                with suppress(Exception):
                    await pubsub.aclose()


manager = ConnectionManager()
