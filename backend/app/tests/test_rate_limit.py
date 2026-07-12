import pytest
from fastapi import HTTPException
from starlette.requests import Request

from app.core import rate_limit


class FakeRedis:
    def __init__(self) -> None:
        self.values: dict[str, int] = {}

    async def eval(self, script: str, key_count: int, key: str, ttl: int) -> int:
        self.values[key] = self.values.get(key, 0) + 1
        return self.values[key]


def request() -> Request:
    return Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/auth/login",
            "headers": [],
            "client": ("192.0.2.10", 12345),
            "scheme": "https",
            "server": ("relay.example.com", 443),
        }
    )


async def test_auth_rate_limit_is_shared_through_redis(monkeypatch) -> None:
    redis = FakeRedis()

    async def fake_get_redis() -> FakeRedis:
        return redis

    monkeypatch.setattr(rate_limit, "get_redis", fake_get_redis)

    for _ in range(rate_limit.MAX_ATTEMPTS):
        await rate_limit.auth_rate_limit(request())

    with pytest.raises(HTTPException) as raised:
        await rate_limit.auth_rate_limit(request())

    assert raised.value.status_code == 429
    assert len(redis.values) == 1
