import asyncio
import json
from collections import defaultdict
from uuid import uuid4

from fastapi import WebSocket, WebSocketDisconnect
from redis.asyncio import Redis


class ConnectionManager:
    def __init__(self) -> None:
        self.instance_id = str(uuid4())
        self.user_connections: dict[str, set[WebSocket]] = defaultdict(set)
        self.rooms: dict[str, set[str]] = defaultdict(set)
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
            for members in self.rooms.values():
                members.discard(user_id)

    async def join_room(self, conversation_id: str, user_id: str) -> None:
        async with self._lock:
            self.rooms[conversation_id].add(user_id)

    async def leave_room(self, conversation_id: str, user_id: str) -> None:
        async with self._lock:
            self.rooms[conversation_id].discard(user_id)

    def is_connected(self, user_id: str) -> bool:
        return bool(self.user_connections.get(user_id))

    def is_in_room(self, conversation_id: str, user_id: str) -> bool:
        return user_id in self.rooms.get(conversation_id, set())

    async def send_to_user(self, user_id: str, event: dict) -> None:
        connections = list(self.user_connections.get(user_id, set()))
        stale: list[WebSocket] = []
        for websocket in connections:
            try:
                await websocket.send_json(event)
            except (RuntimeError, WebSocketDisconnect):
                stale.append(websocket)
        if stale:
            async with self._lock:
                for websocket in stale:
                    self.user_connections.get(user_id, set()).discard(websocket)

    async def broadcast_to_users(
        self, redis: Redis, user_ids: list[str], event_type: str, payload: dict
    ) -> None:
        event = {"type": event_type, "payload": payload}
        for user_id in set(user_ids):
            await self.send_to_user(user_id, event)
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

    async def redis_subscriber(self, redis: Redis) -> None:
        pubsub = redis.pubsub()
        await pubsub.subscribe("pubsub:broadcast")
        async for message in pubsub.listen():
            if message.get("type") != "message":
                continue
            data = json.loads(message["data"])
            if data.get("origin") == self.instance_id:
                continue
            for user_id in data.get("user_ids", []):
                await self.send_to_user(user_id, data["event"])


manager = ConnectionManager()
