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

from app import models  # noqa: E402,F401
from app.api.routes import conversations as conversations_route  # noqa: E402
from app.api.routes import messages as messages_route  # noqa: E402
from app.api.routes import users as users_route  # noqa: E402
from app.core.database import Base, get_db  # noqa: E402
from app.core.rate_limit import auth_rate_limit, clear_auth_rate_limit  # noqa: E402
from app.main import app  # noqa: E402


class FakeRedis:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}
        self.presence: dict[str, dict[str, float]] = {}

    async def ping(self) -> bool:
        return True

    async def set(self, key: str, value: str, ex: int | None = None) -> None:
        self.values[key] = value

    async def delete(self, key: str) -> None:
        self.values.pop(key, None)

    async def exists(self, key: str) -> int:
        return int(key in self.values)

    async def mget(self, keys: list[str]) -> list[str | None]:
        return [self.values.get(key) for key in keys]

    async def publish(self, channel: str, value: str) -> int:
        return 0

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
        raise AssertionError("Unexpected Redis script")


@pytest.fixture()
async def client(tmp_path: Path) -> AsyncGenerator[AsyncClient, None]:
    clear_auth_rate_limit()
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async def override_db() -> AsyncGenerator[AsyncSession, None]:
        async with Session() as session:
            yield session

    fake_redis = FakeRedis()

    async def fake_get_redis() -> FakeRedis:
        return fake_redis

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[auth_rate_limit] = lambda: None
    users_route.get_redis = fake_get_redis
    conversations_route.get_redis = fake_get_redis
    messages_route.get_redis = fake_get_redis

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
