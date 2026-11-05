from httpx import AsyncClient

from app.tests.conftest import register


def auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def _pair(client: AsyncClient):
    alice = await register(client, "alice", "alice@example.com")
    bob = await register(client, "bob", "bob@example.com")
    charlie = await register(client, "charlie", "charlie@example.com")
    return alice, bob, charlie


async def _chat(client: AsyncClient, alice, bob) -> str:
    created = await client.post(
        "/conversations",
        json={"participant_id": bob["user"]["id"]},
        headers=auth_headers(alice["access_token"]),
    )
    assert created.status_code == 200, created.text
    return created.json()["id"]


async def _search(client: AsyncClient, user, q: str):
    return await client.get(
        f"/users/search?q={q}", headers=auth_headers(user["access_token"])
    )


async def test_block_hides_from_search_both_directions(client: AsyncClient) -> None:
    alice, bob, _charlie = await _pair(client)
    bob_id = bob["user"]["id"]

    before = await _search(client, alice, "bob")
    assert before.status_code == 200
    assert any(u["id"] == bob_id for u in before.json())

    blocked = await client.post(
        f"/users/{bob_id}/block", headers=auth_headers(alice["access_token"])
    )
    assert blocked.status_code == 204, blocked.text

    alice_view = await _search(client, alice, "bob")
    assert alice_view.json() == []

    bob_view = await _search(client, bob, "alice")
    assert bob_view.json() == []

    # Third user still sees both.
    third = await _search(client, _charlie, "bob")
    assert any(u["id"] == bob_id for u in third.json())


async def test_unblock_restores_visibility(client: AsyncClient) -> None:
    alice, bob, _charlie = await _pair(client)
    bob_id = bob["user"]["id"]
    await client.post(f"/users/{bob_id}/block", headers=auth_headers(alice["access_token"]))
    unblocked = await client.delete(
        f"/users/{bob_id}/block", headers=auth_headers(alice["access_token"])
    )
    assert unblocked.status_code == 204
    view = await _search(client, alice, "bob")
    assert any(u["id"] == bob_id for u in view.json())


async def test_block_guards(client: AsyncClient) -> None:
    alice, bob, _charlie = await _pair(client)
    alice_id = alice["user"]["id"]
    bob_id = bob["user"]["id"]

    self_block = await client.post(
        f"/users/{alice_id}/block", headers=auth_headers(alice["access_token"])
    )
    assert self_block.status_code == 400

    unknown = await client.post(
        "/users/nonexistent-id/block", headers=auth_headers(alice["access_token"])
    )
    assert unknown.status_code == 404

    # Idempotent re-block.
    first = await client.post(f"/users/{bob_id}/block", headers=auth_headers(alice["access_token"]))
    second = await client.post(
        f"/users/{bob_id}/block", headers=auth_headers(alice["access_token"])
    )
    assert first.status_code == 204
    assert second.status_code == 204


async def test_blocked_list(client: AsyncClient) -> None:
    alice, bob, _charlie = await _pair(client)
    await client.post(
        f"/users/{bob['user']['id']}/block", headers=auth_headers(alice["access_token"])
    )
    response = await client.get(
        "/users/me/blocked", headers=auth_headers(alice["access_token"])
    )
    assert response.status_code == 200
    assert [u["id"] for u in response.json()] == [bob["user"]["id"]]
    bob_list = await client.get(
        "/users/me/blocked", headers=auth_headers(bob["access_token"])
    )
    assert bob_list.json() == []


async def test_message_rejected_when_blocked(client: AsyncClient) -> None:
    alice, bob, _charlie = await _pair(client)
    conversation_id = await _chat(client, alice, bob)
    await client.post(
        f"/users/{bob['user']['id']}/block", headers=auth_headers(alice["access_token"])
    )

    from_alice = await client.post(
        "/messages",
        headers=auth_headers(alice["access_token"]),
        json={
            "conversation_id": conversation_id,
            "client_message_id": "m1",
            "text": "hello",
        },
    )
    assert from_alice.status_code == 404, from_alice.text

    from_bob = await client.post(
        "/messages",
        headers=auth_headers(bob["access_token"]),
        json={
            "conversation_id": conversation_id,
            "client_message_id": "m2",
            "text": "hi",
        },
    )
    assert from_bob.status_code == 404, from_bob.text


async def test_create_conversation_rejected_when_blocked(client: AsyncClient) -> None:
    alice, bob, _charlie = await _pair(client)
    await client.post(
        f"/users/{bob['user']['id']}/block", headers=auth_headers(alice["access_token"])
    )
    created = await client.post(
        "/conversations",
        json={"participant_id": bob["user"]["id"]},
        headers=auth_headers(alice["access_token"]),
    )
    assert created.status_code == 404, created.text
    # Reverse direction too.
    created_back = await client.post(
        "/conversations",
        json={"participant_id": alice["user"]["id"]},
        headers=auth_headers(bob["access_token"]),
    )
    assert created_back.status_code == 404, created_back.text


async def test_group_messages_not_blocked(client: AsyncClient) -> None:
    """Blocking only constrains 1:1 chats; group messages still work."""
    alice, bob, charlie = await _pair(client)
    group = await client.post(
        "/conversations/group",
        json={"title": "Crew", "participant_ids": [bob["user"]["id"], charlie["user"]["id"]]},
        headers=auth_headers(alice["access_token"]),
    )
    assert group.status_code == 201, group.text
    conversation_id = group.json()["id"]
    await client.post(
        f"/users/{bob['user']['id']}/block", headers=auth_headers(alice["access_token"])
    )
    sent = await client.post(
        "/messages",
        headers=auth_headers(alice["access_token"]),
        json={
            "conversation_id": conversation_id,
            "client_message_id": "g1",
            "text": "hey crew",
        },
    )
    assert sent.status_code == 201, sent.text
