from hashlib import sha256
from time import time

from fastapi import HTTPException, Request, status
from redis.exceptions import RedisError

from app.core.redis import get_redis

WINDOW_SECONDS = 60
MAX_ATTEMPTS = 20
INCREMENT_WITH_EXPIRY = """
local current = redis.call('INCR', KEYS[1])
if current == 1 then
  redis.call('EXPIRE', KEYS[1], ARGV[1])
end
return current
"""


def clear_auth_rate_limit() -> None:
    """Retained for compatibility with older test fixtures."""


async def auth_rate_limit(request: Request) -> None:
    client = request.client.host if request.client else "unknown"
    window = int(time() // WINDOW_SECONDS)
    identity = sha256(f"{client}:{request.url.path}:{window}".encode()).hexdigest()
    key = f"rate_limit:auth:{identity}"
    try:
        redis = await get_redis()
        attempts = int(
            await redis.eval(INCREMENT_WITH_EXPIRY, 1, key, WINDOW_SECONDS + 1)
        )
    except RedisError as exc:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "Authentication temporarily unavailable",
        ) from exc
    if attempts > MAX_ATTEMPTS:
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Too many attempts, try again later")
