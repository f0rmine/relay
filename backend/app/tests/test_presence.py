from app.services.presence import is_online, set_offline, set_online
from app.tests.conftest import FakeRedis


async def test_presence_remains_online_while_another_instance_is_connected() -> None:
    redis = FakeRedis()

    assert await set_online(redis, "user-1", "instance-a") is True
    assert await set_online(redis, "user-1", "instance-b") is False
    assert await is_online(redis, "user-1") is True

    assert await set_offline(redis, "user-1", "instance-a") is True
    assert await is_online(redis, "user-1") is True

    assert await set_offline(redis, "user-1", "instance-b") is False
    assert await is_online(redis, "user-1") is False
