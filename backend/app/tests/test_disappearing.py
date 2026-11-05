from datetime import UTC, datetime, timedelta

from httpx import AsyncClient

from app.tests.conftest import register


def auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def _chat(client: AsyncClient):
    alice = await register(client, "alice", "alice@example.com")
    bob = await register(client, "bob", "bob@example.com")
    created = await client.post(
        "/conversations",
        json={"participant_id": bob["user"]["id"]},
        headers=auth_headers(alice["access_token"]),
    )
    assert created.status_code == 200, created.text
    return alice, bob, created.json()["id"]


async def _send(client: AsyncClient, alice, conversation_id: str, client_message_id: str):
    return await client.post(
        "/messages",
        headers=auth_headers(alice["access_token"]),
        json={
            "conversation_id": conversation_id,
            "client_message_id": client_message_id,
            "text": "vanishing act",
        },
    )


async def _message_expires_at(message_id: str):
    from sqlalchemy import select

    from app.core.database import get_db
    from app.main import app
    from app.models.message import Message

    override = app.dependency_overrides[get_db]
    async for db in override():
        message = (await db.scalars(select(Message).where(Message.id == message_id))).first()
        return message.expires_at if message else None
    return None


async def test_set_ttl_and_message_expires_at(client: AsyncClient) -> None:
    alice, _bob, conversation_id = await _chat(client)
    patched = await client.patch(
        f"/conversations/{conversation_id}/disappearing",
        json={"seconds": 3600},
        headers=auth_headers(alice["access_token"]),
    )
    assert patched.status_code == 200, patched.text
    assert patched.json()["disappearing_after_seconds"] == 3600

    sent = await _send(client, alice, conversation_id, "d1")
    assert sent.status_code == 201, sent.text
    expires_at = await _message_expires_at(sent.json()["id"])
    assert expires_at is not None
    soon = datetime.now(UTC) + timedelta(minutes=59, seconds=30)
    later = datetime.now(UTC) + timedelta(minutes=60, seconds=30)
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)
    assert soon <= expires_at <= later


async def test_no_ttl_never_expires(client: AsyncClient) -> None:
    alice, _bob, conversation_id = await _chat(client)
    sent = await _send(client, alice, conversation_id, "n1")
    assert sent.status_code == 201, sent.text
    assert await _message_expires_at(sent.json()["id"]) is None


async def test_sweep_deletes_expired(client: AsyncClient) -> None:
    from sqlalchemy import select

    from app.core.database import get_db
    from app.main import app
    from app.models.message import Message
    from app.services.messages import sweep_disappearing_messages

    alice, bob, conversation_id = await _chat(client)
    await client.patch(
        f"/conversations/{conversation_id}/disappearing",
        json={"seconds": 3600},
        headers=auth_headers(alice["access_token"]),
    )
    sent = await _send(client, alice, conversation_id, "s1")
    assert sent.status_code == 201
    message_id = sent.json()["id"]

    override = app.dependency_overrides[get_db]
    async for db in override():
        message = (await db.scalars(select(Message).where(Message.id == message_id))).first()
        message.expires_at = datetime.now(UTC) - timedelta(seconds=5)
        await db.commit()
        break

    # Sweeper deletes it.
    async for db in override():
        count = await sweep_disappearing_messages(db)
        assert count == 1
        gone = (await db.scalars(select(Message).where(Message.id == message_id))).first()
        assert gone is None
        break

    # Not-yet expired messages survive a sweep.
    sent2 = await _send(client, alice, conversation_id, "s2")
    assert sent2.status_code == 201
    async for db in override():
        assert await sweep_disappearing_messages(db) == 0
        break
    history = await client.get(
        f"/conversations/{conversation_id}/messages",
        headers=auth_headers(bob["access_token"]),
    )
    assert [item["id"] for item in history.json()["items"]] == [sent2.json()["id"]]


async def test_expired_hidden_before_sweep(client: AsyncClient) -> None:
    from sqlalchemy import select

    from app.core.database import get_db
    from app.main import app
    from app.models.message import Message

    alice, bob, conversation_id = await _chat(client)
    await client.patch(
        f"/conversations/{conversation_id}/disappearing",
        json={"seconds": 3600},
        headers=auth_headers(alice["access_token"]),
    )
    sent = await _send(client, alice, conversation_id, "h1")
    assert sent.status_code == 201

    override = app.dependency_overrides[get_db]
    async for db in override():
        message = (
            await db.scalars(select(Message).where(Message.id == sent.json()["id"]))
        ).first()
        message.expires_at = datetime.now(UTC) - timedelta(seconds=1)
        await db.commit()
        break

    history = await client.get(
        f"/conversations/{conversation_id}/messages",
        headers=auth_headers(bob["access_token"]),
    )
    assert history.json()["items"] == []
    conversations = await client.get(
        "/conversations", headers=auth_headers(bob["access_token"])
    )
    by_id = {c["id"]: c for c in conversations.json()}
    assert by_id[conversation_id]["latest_message"] is None
    assert by_id[conversation_id]["unread_count"] == 0


async def test_ttl_validation_and_off(client: AsyncClient) -> None:
    alice, _bob, conversation_id = await _chat(client)
    too_big = await client.patch(
        f"/conversations/{conversation_id}/disappearing",
        json={"seconds": 31 * 24 * 3600},
        headers=auth_headers(alice["access_token"]),
    )
    assert too_big.status_code == 400, too_big.text

    negative = await client.patch(
        f"/conversations/{conversation_id}/disappearing",
        json={"seconds": -5},
        headers=auth_headers(alice["access_token"]),
    )
    assert negative.status_code == 400

    off = await client.patch(
        f"/conversations/{conversation_id}/disappearing",
        json={"seconds": None},
        headers=auth_headers(alice["access_token"]),
    )
    assert off.status_code == 200
    assert off.json()["disappearing_after_seconds"] is None

    sent = await _send(client, alice, conversation_id, "o1")
    assert sent.status_code == 201
    assert await _message_expires_at(sent.json()["id"]) is None
