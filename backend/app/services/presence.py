import asyncio
from datetime import UTC, datetime

from redis.asyncio import Redis

PRESENCE_TTL_SECONDS = 45
TYPING_TTL_SECONDS = 5
SET_ONLINE_SCRIPT = """
redis.call('ZREMRANGEBYSCORE', KEYS[1], '-inf', ARGV[1])
local existing = redis.call('ZCARD', KEYS[1])
redis.call('ZADD', KEYS[1], ARGV[2], ARGV[3])
redis.call('EXPIRE', KEYS[1], ARGV[4])
if existing == 0 then return 1 else return 0 end
"""
SET_OFFLINE_SCRIPT = """
redis.call('ZREM', KEYS[1], ARGV[1])
redis.call('ZREMRANGEBYSCORE', KEYS[1], '-inf', ARGV[2])
return redis.call('ZCARD', KEYS[1])
"""
IS_ONLINE_SCRIPT = """
redis.call('ZREMRANGEBYSCORE', KEYS[1], '-inf', ARGV[1])
return redis.call('ZCARD', KEYS[1])
"""


def presence_key(user_id: str) -> str:
    return f"presence:user:{user_id}"


def typing_key(conversation_id: str, user_id: str) -> str:
    return f"typing:conversation:{conversation_id}:user:{user_id}"


async def set_online(redis: Redis, user_id: str, instance_id: str) -> bool:
    now = datetime.now(UTC).timestamp()
    became_online = await redis.eval(
        SET_ONLINE_SCRIPT,
        1,
        presence_key(user_id),
        now,
        now + PRESENCE_TTL_SECONDS,
        instance_id,
        PRESENCE_TTL_SECONDS * 2,
    )
    return bool(became_online)


async def set_offline(redis: Redis, user_id: str, instance_id: str) -> bool:
    remaining = await redis.eval(
        SET_OFFLINE_SCRIPT,
        1,
        presence_key(user_id),
        instance_id,
        datetime.now(UTC).timestamp(),
    )
    return bool(remaining)


async def is_online(redis: Redis, user_id: str) -> bool:
    remaining = await redis.eval(
        IS_ONLINE_SCRIPT,
        1,
        presence_key(user_id),
        datetime.now(UTC).timestamp(),
    )
    return bool(remaining)


async def online_map(redis: Redis, user_ids: list[str]) -> dict[str, bool]:
    if not user_ids:
        return {}
    values = await asyncio.gather(*(is_online(redis, user_id) for user_id in user_ids))
    return dict(zip(user_ids, values, strict=False))


async def set_typing(redis: Redis, conversation_id: str, user_id: str) -> None:
    await redis.set(typing_key(conversation_id, user_id), "1", ex=TYPING_TTL_SECONDS)


async def clear_typing(redis: Redis, conversation_id: str, user_id: str) -> None:
    await redis.delete(typing_key(conversation_id, user_id))
