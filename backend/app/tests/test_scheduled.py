from datetime import UTC, datetime, timedelta

from httpx import AsyncClient

from app.tests.conftest import register


def auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def _make_chat(client: AsyncClient):
    alice = await register(client, "alice", "alice@example.com")
    bob = await register(client, "bob", "bob@example.com")
    charlie = await register(client, "charlie", "charlie@example.com")
    created = await client.post(
        "/conversations",
        json={"participant_id": bob["user"]["id"]},
        headers=auth_headers(alice["access_token"]),
    )
    assert created.status_code == 200, created.text
    conversation_id = created.json()["id"]
    return alice, bob, charlie, conversation_id


async def test_scheduled_message_hidden_until_due(client: AsyncClient, monkeypatch) -> None:
    alice, bob, _charlie, conversation_id = await _make_chat(client)
    from app.core.database import get_db
    from app.main import app
    from app.models.message import Message
    from app.services.messages import dispatch_due_messages_once

    future = (datetime.now(UTC) + timedelta(hours=1)).isoformat()
    sent = await client.post(
        "/messages",
        headers=auth_headers(alice["access_token"]),
        json={
            "conversation_id": conversation_id,
            "client_message_id": "sched-1",
            "text": "see you later",
            "scheduled_at": future,
        },
    )
    assert sent.status_code == 201, sent.text
    message_id = sent.json()["id"]
    assert sent.json()["scheduled_at"] is not None
    assert sent.json()["mentions"] == []

    broadcasts: list = []

    async def fake_broadcast(redis, user_ids, event_type, payload) -> None:
        broadcasts.append((user_ids, event_type, payload))

    from app.websocket import manager as manager_module

    monkeypatch.setattr(manager_module.manager, "broadcast_to_users", fake_broadcast)

    # Recipient sees nothing yet.
    history = await client.get(
        f"/conversations/{conversation_id}/messages",
        headers=auth_headers(bob["access_token"]),
    )
    assert history.status_code == 200, history.text
    assert history.json()["items"] == []

    conversations = await client.get("/conversations", headers=auth_headers(bob["access_token"]))
    assert conversations.status_code == 200
    by_id = {c["id"]: c for c in conversations.json()}
    assert by_id[conversation_id]["unread_count"] == 0
    assert by_id[conversation_id]["first_unread_id"] is None
    assert by_id[conversation_id]["latest_message"] is None

    # Not due: dispatcher does nothing.
    override = app.dependency_overrides[get_db]
    async for db in override():
        count = await dispatch_due_messages_once(db)
        assert count == 0
        break
    assert [event for _, event, _ in broadcasts] == []

    # Make it due (ORM assignment persists reliably with StaticPool test DB).
    override = app.dependency_overrides[get_db]
    async for db in override():
        due_message = await db.get(Message, message_id)
        assert due_message is not None
        due_message.scheduled_at = datetime.now(UTC) - timedelta(seconds=1)
        await db.commit()
        break

    override = app.dependency_overrides[get_db]
    async for db in override():
        count = await dispatch_due_messages_once(db)
        assert count == 1
        break
    assert [event for _, event, _ in broadcasts] == ["message:new", "conversation:updated"]
    assert broadcasts[0][2]["id"] == message_id

    # Now visible.
    history = await client.get(
        f"/conversations/{conversation_id}/messages",
        headers=auth_headers(bob["access_token"]),
    )
    assert len(history.json()["items"]) == 1
    assert history.json()["items"][0]["text"] == "see you later"

    conversations = await client.get("/conversations", headers=auth_headers(bob["access_token"]))
    by_id = {c["id"]: c for c in conversations.json()}
    assert by_id[conversation_id]["unread_count"] == 1
    assert by_id[conversation_id]["first_unread_id"] == message_id
    assert by_id[conversation_id]["latest_message"]["text"] == "see you later"


async def test_sender_can_edit_and_delete_while_pending(client: AsyncClient) -> None:
    alice, bob, _charlie, conversation_id = await _make_chat(client)
    future = (datetime.now(UTC) + timedelta(hours=2)).isoformat()
    sent = await client.post(
        "/messages",
        headers=auth_headers(alice["access_token"]),
        json={
            "conversation_id": conversation_id,
            "client_message_id": "sched-edit",
            "text": "original pending",
            "scheduled_at": future,
        },
    )
    assert sent.status_code == 201, sent.text
    message_id = sent.json()["id"]

    edited = await client.patch(
        f"/messages/{message_id}",
        headers=auth_headers(alice["access_token"]),
        json={"text": "edited pending"},
    )
    assert edited.status_code == 200, edited.text
    assert edited.json()["text"] == "edited pending"

    # Still hidden from recipient.
    history = await client.get(
        f"/conversations/{conversation_id}/messages",
        headers=auth_headers(bob["access_token"]),
    )
    assert history.json()["items"] == []

    deleted = await client.delete(
        f"/messages/{message_id}", headers=auth_headers(alice["access_token"])
    )
    assert deleted.status_code == 200, deleted.text
    assert deleted.json()["deleted_at"] is not None


async def test_scheduled_beyond_30_days_rejected(client: AsyncClient) -> None:
    alice, _bob, _charlie, conversation_id = await _make_chat(client)
    far = (datetime.now(UTC) + timedelta(days=31)).isoformat()
    rejected = await client.post(
        "/messages",
        headers=auth_headers(alice["access_token"]),
        json={
            "conversation_id": conversation_id,
            "client_message_id": "sched-far",
            "text": "too far",
            "scheduled_at": far,
        },
    )
    assert rejected.status_code == 422, rejected.text


async def test_mentions_stored_and_filtered_to_participants(client: AsyncClient) -> None:
    alice, bob, charlie, conversation_id = await _make_chat(client)
    sent = await client.post(
        "/messages",
        headers=auth_headers(alice["access_token"]),
        json={
            "conversation_id": conversation_id,
            "client_message_id": "mention-1",
            "text": "hi @bob",
            "mentions": [bob["user"]["id"], charlie["user"]["id"], "not-a-user-id"],
        },
    )
    assert sent.status_code == 201, sent.text
    # charlie is not a participant of the private chat -> filtered out.
    assert sent.json()["mentions"] == [bob["user"]["id"]]

    history = await client.get(
        f"/conversations/{conversation_id}/messages",
        headers=auth_headers(bob["access_token"]),
    )
    assert history.json()["items"][0]["mentions"] == [bob["user"]["id"]]
