from httpx import AsyncClient

from app.api.routes import messages as messages_route
from app.tests.conftest import register
from app.tests.test_e2ee import Keys, auth, body


async def keyed_user(client: AsyncClient, name: str, device_ids=("device-one",)):
    user = await register(client, name, f"{name}@example.com")
    keys = Keys()
    response = await client.put(
        "/e2ee/identity", json={"identity_key": keys.identity_b64}, headers=auth(user)
    )
    assert response.status_code == 200, response.text
    for device_id in device_ids:
        device = keys.device(user["user"]["id"], device_id)
        response = await client.post("/e2ee/devices", json=body(device), headers=auth(user))
        assert response.status_code == 200, response.text
    return user


async def e2ee_chat(client: AsyncClient, alice, bob) -> str:
    response = await client.post(
        "/conversations",
        json={"participant_id": bob["user"]["id"], "e2ee": True},
        headers=auth(alice),
    )
    assert response.status_code == 200, response.text
    assert response.json()["e2ee"] is True
    return response.json()["id"]


def envelope(user, device_id: str, tag: str = "x") -> dict:
    return {
        "user_id": user["user"]["id"],
        "device_id": device_id,
        "ciphertext": f"ciphertext-{tag}-{device_id}",
    }


async def send(client, sender, conversation_id, envelopes, client_id="c1", device="device-one"):
    return await client.post(
        "/messages",
        json={
            "conversation_id": conversation_id,
            "client_message_id": client_id,
            "envelopes": envelopes,
            "sender_device_id": device,
        },
        headers=auth(sender),
    )


async def test_e2ee_chat_requires_keys_and_is_separate_from_legacy(client: AsyncClient) -> None:
    alice = await keyed_user(client, "alice")
    bob = await register(client, "bob", "bob@example.com")
    refused = await client.post(
        "/conversations",
        json={"participant_id": bob["user"]["id"], "e2ee": True},
        headers=auth(alice),
    )
    assert refused.status_code == 409

    legacy = await client.post(
        "/conversations", json={"participant_id": bob["user"]["id"]}, headers=auth(alice)
    )
    assert legacy.json()["e2ee"] is False
    bob = await keyed_user(client, "carol")  # a keyed peer
    secure = await e2ee_chat(client, alice, bob)
    again = await e2ee_chat(client, alice, bob)
    assert secure == again


async def test_plaintext_and_edits_are_refused_in_e2ee_chats(client: AsyncClient) -> None:
    alice = await keyed_user(client, "alice")
    bob = await keyed_user(client, "bob")
    chat = await e2ee_chat(client, alice, bob)
    plaintext = await client.post(
        "/messages",
        json={"conversation_id": chat, "client_message_id": "p1", "text": "hello server"},
        headers=auth(alice),
    )
    assert plaintext.status_code == 400

    sent = await send(client, alice, chat, [envelope(bob, "device-one")])
    assert sent.status_code == 201, sent.text
    edit = await client.patch(
        f"/messages/{sent.json()['id']}", json={"text": "edited"}, headers=auth(alice)
    )
    assert edit.status_code == 400


async def test_envelopes_must_cover_exactly_the_active_devices(client: AsyncClient) -> None:
    alice = await keyed_user(client, "alice", ("device-one", "device-two"))
    bob = await keyed_user(client, "bob", ("device-one", "device-two"))
    chat = await e2ee_chat(client, alice, bob)

    missing = await send(client, alice, chat, [envelope(bob, "device-one")])
    assert missing.status_code == 409
    detail = missing.json()["detail"]
    assert detail["code"] == "device_mismatch"
    assert {"user_id": bob["user"]["id"], "device_id": "device-two"} in detail["missing"]
    # The sender's *other* device must be included too (multi-device sync).
    assert {"user_id": alice["user"]["id"], "device_id": "device-two"} in detail["missing"]

    extra = await send(
        client,
        alice,
        chat,
        [
            envelope(bob, "device-one"),
            envelope(bob, "device-two"),
            envelope(alice, "device-two"),
            envelope(bob, "device-ghost"),
        ],
    )
    assert extra.status_code == 409
    assert extra.json()["detail"]["extra"] == [{"user_id": bob["user"]["id"], "device_id": "device-ghost"}]

    ok = await send(
        client,
        alice,
        chat,
        [envelope(bob, "device-one"), envelope(bob, "device-two"), envelope(alice, "device-two")],
    )
    assert ok.status_code == 201, ok.text
    message = ok.json()
    assert message["e2ee"] is True
    assert message["text"] is None
    assert message["sender_device_id"] == "device-one"


async def test_each_device_sees_only_its_own_envelope(client: AsyncClient) -> None:
    alice = await keyed_user(client, "alice")
    bob = await keyed_user(client, "bob", ("device-one", "device-two"))
    chat = await e2ee_chat(client, alice, bob)
    sent = await send(client, alice, chat, [envelope(bob, "device-one"), envelope(bob, "device-two")])
    message_id = sent.json()["id"]

    async def history(user, device: str | None):
        headers = {**auth(user), **({"X-Relay-Device": device} if device else {})}
        response = await client.get(f"/conversations/{chat}/messages", headers=headers)
        assert response.status_code == 200, response.text
        return response.json()["items"][0]["envelope"]

    assert await history(bob, "device-one") == "ciphertext-x-device-one"
    assert await history(bob, "device-two") == "ciphertext-x-device-two"
    assert await history(bob, None) is None
    # Alice naming Bob's device id still gets nothing: lookups are scoped to the caller.
    assert await history(alice, "device-one") is None

    fallback = await client.get(
        f"/messages/{message_id}/envelope", headers={**auth(bob), "X-Relay-Device": "device-two"}
    )
    assert fallback.json()["envelope"] == "ciphertext-x-device-two"


async def test_live_delivery_is_split_per_user(client: AsyncClient, monkeypatch) -> None:
    calls: list[tuple[list[str], str, dict]] = []

    async def capture(_redis, user_ids, event, payload):
        calls.append((list(user_ids), event, payload))

    monkeypatch.setattr(messages_route.manager, "broadcast_to_users", capture)
    alice = await keyed_user(client, "alice", ("device-one", "device-two"))
    bob = await keyed_user(client, "bob")
    chat = await e2ee_chat(client, alice, bob)
    sent = await send(client, alice, chat, [envelope(bob, "device-one"), envelope(alice, "device-two")])
    assert sent.status_code == 201, sent.text

    new_events = {tuple(ids): payload for ids, event, payload in calls if event == "message:new"}
    assert new_events[(bob["user"]["id"],)]["envelopes"] == {"device-one": "ciphertext-x-device-one"}
    assert new_events[(alice["user"]["id"],)]["envelopes"] == {"device-two": "ciphertext-x-device-two"}


async def test_idempotent_resend_and_unknown_device(client: AsyncClient) -> None:
    alice = await keyed_user(client, "alice")
    bob = await keyed_user(client, "bob")
    chat = await e2ee_chat(client, alice, bob)
    first = await send(client, alice, chat, [envelope(bob, "device-one")])
    again = await send(client, alice, chat, [envelope(bob, "device-one")])
    assert again.status_code == 200
    assert again.json()["id"] == first.json()["id"]

    unknown = await send(client, alice, chat, [envelope(bob, "device-one")], "c2", device="device-zzz")
    assert unknown.status_code == 403


async def test_delete_for_everyone_drops_envelopes(client: AsyncClient) -> None:
    alice = await keyed_user(client, "alice")
    bob = await keyed_user(client, "bob")
    chat = await e2ee_chat(client, alice, bob)
    sent = await send(client, alice, chat, [envelope(bob, "device-one")])
    message_id = sent.json()["id"]
    deleted = await client.delete(f"/messages/{message_id}", headers=auth(alice))
    assert deleted.status_code == 200, deleted.text
    gone = await client.get(
        f"/messages/{message_id}/envelope", headers={**auth(bob), "X-Relay-Device": "device-one"}
    )
    assert gone.status_code == 404


async def test_validation_rejects_mixed_content(client: AsyncClient) -> None:
    alice = await keyed_user(client, "alice")
    bob = await keyed_user(client, "bob")
    chat = await e2ee_chat(client, alice, bob)
    mixed = await client.post(
        "/messages",
        json={
            "conversation_id": chat,
            "client_message_id": "m1",
            "text": "leak",
            "envelopes": [envelope(bob, "device-one")],
            "sender_device_id": "device-one",
        },
        headers=auth(alice),
    )
    assert mixed.status_code == 422
