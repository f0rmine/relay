from hashlib import sha256
from time import time
from uuid import uuid4

from fastapi import HTTPException, Request, status
from redis.exceptions import RedisError

from app.core.config import get_settings
from app.core.redis import get_redis

WINDOW_SECONDS = 60
MAX_ATTEMPTS = 20
SLIDING_WINDOW_SCRIPT = """
local cutoff = ARGV[1]
local now_ms = ARGV[2]
local limit = tonumber(ARGV[3])
local member = ARGV[4]
local ttl_ms = ARGV[5]
redis.call('ZREMRANGEBYSCORE', KEYS[1], '-inf', cutoff)
local count = redis.call('ZCARD', KEYS[1])
if count >= limit then
  return count + 1
end
redis.call('ZADD', KEYS[1], now_ms, member)
if count == 0 then
  redis.call('PEXPIRE', KEYS[1], ttl_ms)
end
return count + 1
"""


def clear_auth_rate_limit() -> None:
    """Retained for compatibility with older test fixtures."""


async def hit_rate_limit(key: str, limit: int, window_seconds: int = WINDOW_SECONDS) -> bool:
    """Record one hit and return True when it is still inside the limit."""
    now = time()
    try:
        redis = await get_redis()
        attempts = int(
            await redis.eval(
                SLIDING_WINDOW_SCRIPT,
                1,
                key,
                f"{now - window_seconds:.3f}",
                f"{now * 1000:.0f}",
                str(limit),
                str(uuid4()),
                str(window_seconds * 2000),
            )
        )
    except RedisError as exc:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "Authentication temporarily unavailable",
        ) from exc
    return attempts <= limit


async def auth_rate_limit(request: Request) -> None:
    client = request.client.host if request.client else "unknown"
    identity = sha256(f"{client}:{request.url.path}".encode()).hexdigest()
    allowed = await hit_rate_limit(f"rate_limit:auth:{identity}", MAX_ATTEMPTS)
    if not allowed:
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Too many attempts, try again later")


async def consume_message_allowance(user_id: str) -> bool:
    settings = get_settings()
    return await hit_rate_limit(
        f"rate_limit:messages:{user_id}", settings.message_rate_limit_per_minute
    )


async def consume_ws_auth_allowance(ip: str) -> bool:
    return await hit_rate_limit(f"rate_limit:ws-auth:{ip}", MAX_ATTEMPTS)
