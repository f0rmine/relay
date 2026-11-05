from httpx import AsyncClient

from app.tests.conftest import register


def auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def _users(client: AsyncClient):
    alice = await register(client, "alice", "alice@example.com")
    bob = await register(client, "bob", "bob@example.com")
    charlie = await register(client, "charlie", "charlie@example.com")
    dave = await register(client, "dave", "dave@example.com")
    return alice, bob, charlie, dave


async def _group(client: AsyncClient, alice, bob, charlie) -> str:
    created = await client.post(
        "/conversations/group",
        json={
            "title": "Crew",
            "participant_ids": [bob["user"]["id"], charlie["user"]["id"]],
        },
        headers=auth_headers(alice["access_token"]),
    )
    assert created.status_code == 201, created.text
    return created.json()["id"]


async def test_invite_preview_join(client: AsyncClient) -> None:
    alice, bob, charlie, dave = await _users(client)
    conversation_id = await _group(client, alice, bob, charlie)

    created = await client.post(
        f"/conversations/{conversation_id}/invite",
        headers=auth_headers(alice["access_token"]),
    )
    assert created.status_code == 200, created.text
    token = created.json()["token"]
    assert created.json()["invite_url"] == f"/invite/{token}"
    assert token

    # Idempotent: same token on re-request.
    again = await client.post(
        f"/conversations/{conversation_id}/invite",
        headers=auth_headers(alice["access_token"]),
    )
    assert again.json()["token"] == token

    preview = await client.get(
        f"/invite/{token}", headers=auth_headers(dave["access_token"])
    )
    assert preview.status_code == 200, preview.text
    body = preview.json()
    assert body["conversation_id"] == conversation_id
    assert body["title"] == "Crew"
    assert body["participant_count"] == 3
    assert body["is_member"] is False

    member_preview = await client.get(
        f"/invite/{token}", headers=auth_headers(bob["access_token"])
    )
    assert member_preview.json()["is_member"] is True

    joined = await client.post(
        f"/invite/{token}/join", headers=auth_headers(dave["access_token"])
    )
    assert joined.status_code == 200, joined.text
    assert joined.json()["id"] == conversation_id
    participant_ids = {p["id"] for p in joined.json()["participants"]}
    assert dave["user"]["id"] in participant_ids

    # Idempotent re-join.
    rejoined = await client.post(
        f"/invite/{token}/join", headers=auth_headers(dave["access_token"])
    )
    assert rejoined.status_code == 200
    preview_after = await client.get(
        f"/invite/{token}", headers=auth_headers(dave["access_token"])
    )
    assert preview_after.json()["is_member"] is True
    assert preview_after.json()["participant_count"] == 4


async def test_revoke_invalidates_old_token(client: AsyncClient) -> None:
    alice, bob, charlie, dave = await _users(client)
    conversation_id = await _group(client, alice, bob, charlie)
    created = await client.post(
        f"/conversations/{conversation_id}/invite",
        headers=auth_headers(alice["access_token"]),
    )
    old_token = created.json()["token"]

    revoked = await client.post(
        f"/conversations/{conversation_id}/invite/revoke",
        headers=auth_headers(alice["access_token"]),
    )
    assert revoked.status_code == 200, revoked.text
    new_token = revoked.json()["token"]
    assert new_token != old_token

    old_preview = await client.get(
        f"/invite/{old_token}", headers=auth_headers(dave["access_token"])
    )
    assert old_preview.status_code == 404

    old_join = await client.post(
        f"/invite/{old_token}/join", headers=auth_headers(dave["access_token"])
    )
    assert old_join.status_code == 404

    new_join = await client.post(
        f"/invite/{new_token}/join", headers=auth_headers(dave["access_token"])
    )
    assert new_join.status_code == 200, new_join.text


async def test_private_chat_invite_rejected(client: AsyncClient) -> None:
    alice, bob, _charlie, _dave = await _users(client)
    created = await client.post(
        "/conversations",
        json={"participant_id": bob["user"]["id"]},
        headers=auth_headers(alice["access_token"]),
    )
    conversation_id = created.json()["id"]
    invite = await client.post(
        f"/conversations/{conversation_id}/invite",
        headers=auth_headers(alice["access_token"]),
    )
    assert invite.status_code == 400, invite.text
    revoke = await client.post(
        f"/conversations/{conversation_id}/invite/revoke",
        headers=auth_headers(alice["access_token"]),
    )
    assert revoke.status_code == 400, revoke.text


async def test_invalid_token_404(client: AsyncClient) -> None:
    _alice, _bob, _charlie, dave = await _users(client)
    preview = await client.get(
        "/invite/nope", headers=auth_headers(dave["access_token"])
    )
    assert preview.status_code == 404
    join = await client.post(
        "/invite/nope/join", headers=auth_headers(dave["access_token"])
    )
    assert join.status_code == 404


async def test_non_participant_cannot_create_invite(client: AsyncClient) -> None:
    alice, bob, charlie, dave = await _users(client)
    conversation_id = await _group(client, alice, bob, charlie)
    denied = await client.post(
        f"/conversations/{conversation_id}/invite",
        headers=auth_headers(dave["access_token"]),
    )
    assert denied.status_code == 404, denied.text
