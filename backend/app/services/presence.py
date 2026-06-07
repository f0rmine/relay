from datetime import UTC, datetime

from redis.asyncio import Redis

PRESENCE_TTL_SECONDS = 45
TYPING_TTL_SECONDS = 5


def presence_key(user_id: str) -> str:
    return f"presence:user:{user_id}"


def typing_key(conversation_id: str, user_id: str) -> str:
    return f"typing:conversation:{conversation_id}:user:{user_id}"


async def set_online(redis: Redis, user_id: str) -> None:
    await redis.set(presence_key(user_id), datetime.now(UTC).isoformat(), ex=PRESENCE_TTL_SECONDS)


async def set_offline(redis: Redis, user_id: str) -> None:
    await redis.delete(presence_key(user_id))


async def is_online(redis: Redis, user_id: str) -> bool:
    return bool(await redis.exists(presence_key(user_id)))


async def online_map(redis: Redis, user_ids: list[str]) -> dict[str, bool]:
    if not user_ids:
        return {}
    values = await redis.mget([presence_key(user_id) for user_id in user_ids])
    return dict(zip(user_ids, [value is not None for value in values], strict=False))


async def set_typing(redis: Redis, conversation_id: str, user_id: str) -> None:
    await redis.set(typing_key(conversation_id, user_id), "1", ex=TYPING_TTL_SECONDS)


async def clear_typing(redis: Redis, conversation_id: str, user_id: str) -> None:
    await redis.delete(typing_key(conversation_id, user_id))
