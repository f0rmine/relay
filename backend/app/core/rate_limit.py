from collections import defaultdict, deque
from time import monotonic

from fastapi import HTTPException, Request, status

WINDOW_SECONDS = 60
MAX_ATTEMPTS = 20
_attempts: dict[str, deque[float]] = defaultdict(deque)


def clear_auth_rate_limit() -> None:
    _attempts.clear()


async def auth_rate_limit(request: Request) -> None:
    client = request.client.host if request.client else "unknown"
    key = f"{client}:{request.url.path}"
    now = monotonic()
    bucket = _attempts[key]
    while bucket and now - bucket[0] > WINDOW_SECONDS:
        bucket.popleft()
    if len(bucket) >= MAX_ATTEMPTS:
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Too many attempts, try again later")
    bucket.append(now)
