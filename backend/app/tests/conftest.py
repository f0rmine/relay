import asyncio
import os
from collections.abc import AsyncGenerator
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("ENVIRONMENT", "test")
os.environ.setdefault("UPLOAD_DIR", "./test-uploads")
os.environ.setdefault("JWT_SECRET", "test-access-secret-with-at-least-32-bytes")
os.environ.setdefault("JWT_REFRESH_SECRET", "test-refresh-secret-with-at-least-32-bytes")
os.environ.setdefault("PASSWORD_RESET_TOKEN_IN_RESPONSE", "true")
os.environ.setdefault("ENCRYPTION_ACTIVE_KEY_ID", "test-v1")
os.environ.setdefault(
    "ENCRYPTION_KEYS",
    '{"test-v1":"AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8="}',
)

from app import models  # noqa: F401
from app.api import deps as deps_module
from app.api.routes import conversations as conversations_route
from app.api.routes import messages as messages_route
from app.api.routes import users as users_route
from app.core import rate_limit as rate_limit_module
from app.core.database import Base, get_db
from app.core.rate_limit import (
    SLIDING_WINDOW_SCRIPT,
    auth_rate_limit,
    clear_auth_rate_limit,
)
from app.main import app
from app.services import attachments as attachments_module
from app.services import auth as auth_service_module
from app.services import push as push_module


class FakeRedis:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}
        self.presence: dict[str, dict[str, float]] = {}
        self.windows: dict[str, dict[str, float]] = {}
        self.lists: dict[str, list[str]] = {}

    async def ping(self) -> bool:
        return True

    async def set(
        self, key: str, value: str, ex: int | None = None, nx: bool = False
    ) -> str | None:
        if nx and key in self.values:
            return None
        self.values[key] = value
        return "OK"

    async def delete(self, key: str) -> None:
        self.values.pop(key, None)

    async def exists(self, key: str) -> int:
        return int(key in self.values)

    async def incr(self, key: str) -> int:
        value = int(self.values.get(key, 0)) + 1
        self.values[key] = str(value)
        return value

    async def incrby(self, key: str, amount: int) -> int:
        value = int(self.values.get(key, 0)) + amount
        self.values[key] = str(value)
        return value

    async def expire(self, key: str, seconds: int) -> int:
        return int(key in self.values)

    async def get(self, key: str) -> str | None:
        return self.values.get(key)

    async def mget(self, keys: list[str]) -> list[str | None]:
        return [self.values.get(key) for key in keys]

    async def publish(self, channel: str, value: str) -> int:
        return 0

    async def scan(self, cursor: int | str = 0, match: str | None = None, count: int = 100):
        prefix = (match or "*").rstrip("*")
        keys = [key for key in self.presence if key.startswith(prefix)]
        return 0, keys

    async def rpush(self, key: str, value: str) -> int:
        self.lists.setdefault(key, []).append(value)
        return len(self.lists[key])

    async def blpop(self, key: str, timeout: int = 0) -> tuple[str, str] | None:
        queue = self.lists.get(key)
        if not queue:
            await asyncio.sleep(min(timeout, 0.05))
            return None
        return key, queue.pop(0)

    async def eval(self, script: str, key_count: int, key: str, *args) -> int:
        from app.services.presence import IS_ONLINE_SCRIPT, SET_OFFLINE_SCRIPT, SET_ONLINE_SCRIPT

        members = self.presence.setdefault(key, {})
        if script == SET_ONLINE_SCRIPT:
            now, expires_at, instance_id, _ttl = args
            members = {
                member: score for member, score in members.items() if score > float(now)
            }
            became_online = not members
            members[str(instance_id)] = float(expires_at)
            self.presence[key] = members
            return int(became_online)
        if script == SET_OFFLINE_SCRIPT:
            instance_id, now = args
            members.pop(str(instance_id), None)
            self.presence[key] = {
                member: score for member, score in members.items() if score > float(now)
            }
            return len(self.presence[key])
        if script == IS_ONLINE_SCRIPT:
            now = float(args[0])
            self.presence[key] = {
                member: score for member, score in members.items() if score > now
            }
            return len(self.presence[key])
        if script == SLIDING_WINDOW_SCRIPT:
            cutoff, now_ms, limit, member = (
                float(args[0]),
                float(args[1]),
                int(args[2]),
                str(args[3]),
            )
            window = self.windows.setdefault(key, {})
            self.windows[key] = {m: s for m, s in window.items() if s > cutoff}
            count = len(self.windows[key])
            if count < limit:
                self.windows[key][member] = now_ms
            return count + 1
        raise AssertionError("Unexpected Redis script")


@pytest.fixture(autouse=True)
def fake_redis_patches() -> AsyncGenerator[FakeRedis, None]:
    fake_redis = FakeRedis()

    async def fake_get_redis() -> FakeRedis:
        return fake_redis

    users_route.get_redis = fake_get_redis
    conversations_route.get_redis = fake_get_redis
    messages_route.get_redis = fake_get_redis
    deps_module.get_redis = fake_get_redis
    auth_service_module.get_redis = fake_get_redis
    attachments_module.get_redis = fake_get_redis
    push_module.get_redis = fake_get_redis
    rate_limit_module.get_redis = fake_get_redis
    yield fake_redis


@pytest.fixture()
async def client(tmp_path: Path) -> AsyncGenerator[AsyncClient, None]:
    clear_auth_rate_limit()
    database_url = os.environ.get("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
    engine_kwargs: dict = {}
    if database_url.startswith("sqlite"):
        engine_kwargs["connect_args"] = {"check_same_thread": False}
        engine_kwargs["poolclass"] = StaticPool
    engine = create_async_engine(database_url, **engine_kwargs)
    Session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async def override_db() -> AsyncGenerator[AsyncSession, None]:
        async with Session() as session:
            yield session

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[auth_rate_limit] = lambda: None

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as test_client:
        yield test_client

    app.dependency_overrides.clear()
    clear_auth_rate_limit()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


async def register(client: AsyncClient, username: str, email: str) -> dict:
    response = await client.post(
        "/auth/register",
        json={
            "username": username,
            "display_name": username.title(),
            "email": email,
            "password": "password123",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()
