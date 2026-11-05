from types import SimpleNamespace
from urllib.parse import parse_qs, urlparse

from httpx import AsyncClient

from app.tests.conftest import register

PNG_BYTES = b"\x89PNG\r\n\x1a\npayload"


def auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def _make_group(client: AsyncClient):
    alice = await register(client, "alice", "alice@example.com")
    bob = await register(client, "bob", "bob@example.com")
    charlie = await register(client, "charlie", "charlie@example.com")
    created = await client.post(
        "/conversations/group",
        json={
            "title": "Test Group",
            "participant_ids": [bob["user"]["id"], charlie["user"]["id"]],
        },
        headers=auth_headers(alice["access_token"]),
    )
    assert created.status_code == 201, created.text
    return alice, bob, charlie, created.json()


async def test_group_avatar_admin_upload_and_signed_url_served(client: AsyncClient, monkeypatch) -> None:
    alice, bob, _charlie, group = await _make_group(client)
    conversation_id = group["id"]
    assert group.get("avatar_url") is None
    assert group.get("first_unread_id") is None

    from app.api.routes import conversations as conversations_route

    broadcasts: list[tuple[list[str], str, dict]] = []

    async def fake_broadcast(redis, user_ids: list[str], event_type: str, payload: dict) -> None:
        broadcasts.append((user_ids, event_type, payload))

    monkeypatch.setattr(conversations_route.manager, "broadcast_to_users", fake_broadcast)

    uploaded = await client.put(
        f"/conversations/{conversation_id}/avatar",
        headers=auth_headers(alice["access_token"]),
        files={"file": ("avatar.png", PNG_BYTES, "image/png")},
    )
    assert uploaded.status_code == 200, uploaded.text
    avatar_url = uploaded.json()["avatar_url"]
    assert avatar_url is not None
    assert avatar_url.startswith("/uploads/avatars/")
    assert "sig=" in avatar_url and "exp=" in avatar_url

    # Signed URL is served via /users/avatar/{filename}
    parsed = urlparse(avatar_url)
    filename = parsed.path.rsplit("/", 1)[-1]
    query = parse_qs(parsed.query)
    served = await client.get(
        f"/users/avatar/{filename}?exp={query['exp'][0]}&sig={query['sig'][0]}"
    )
    assert served.status_code == 200, served.text
    assert served.content == PNG_BYTES

    # Other participants see the signed avatar via conversation serialization
    fetched = await client.get(
        f"/conversations/{conversation_id}", headers=auth_headers(bob["access_token"])
    )
    assert fetched.status_code == 200
    assert fetched.json()["avatar_url"] == avatar_url

    assert broadcasts and broadcasts[-1][1] == "conversation:updated-info"
    assert broadcasts[-1][2]["avatar_url"] == avatar_url


async def test_group_avatar_non_admin_forbidden(client: AsyncClient) -> None:
    _alice, bob, _charlie, group = await _make_group(client)
    response = await client.put(
        f"/conversations/{group['id']}/avatar",
        headers=auth_headers(bob["access_token"]),
        files={"file": ("avatar.png", PNG_BYTES, "image/png")},
    )
    assert response.status_code == 403


async def test_group_avatar_private_chat_rejected(client: AsyncClient) -> None:
    alice = await register(client, "alice", "alice@example.com")
    bob = await register(client, "bob", "bob@example.com")
    created = await client.post(
        "/conversations",
        json={"participant_id": bob["user"]["id"]},
        headers=auth_headers(alice["access_token"]),
    )
    assert created.status_code == 200, created.text
    conversation_id = created.json()["id"]
    # Private conversations do not expose an avatar_url
    assert created.json().get("avatar_url") is None

    response = await client.put(
        f"/conversations/{conversation_id}/avatar",
        headers=auth_headers(alice["access_token"]),
        files={"file": ("avatar.png", PNG_BYTES, "image/png")},
    )
    assert response.status_code == 400


async def test_group_avatar_invalid_type_rejected(client: AsyncClient) -> None:
    alice, _bob, _charlie, group = await _make_group(client)
    conversation_id = group["id"]

    wrong_type = await client.put(
        f"/conversations/{conversation_id}/avatar",
        headers=auth_headers(alice["access_token"]),
        files={"file": ("avatar.txt", b"hello", "text/plain")},
    )
    assert wrong_type.status_code == 400

    spoofed = await client.put(
        f"/conversations/{conversation_id}/avatar",
        headers=auth_headers(alice["access_token"]),
        files={"file": ("avatar.png", b"not really png", "image/png")},
    )
    assert spoofed.status_code == 400

    empty = await client.put(
        f"/conversations/{conversation_id}/avatar",
        headers=auth_headers(alice["access_token"]),
        files={"file": ("avatar.png", b"", "image/png")},
    )
    assert empty.status_code == 400


async def test_group_avatar_replacement_removes_previous_file(client: AsyncClient, monkeypatch, tmp_path) -> None:
    from app.services import users as users_service

    monkeypatch.setattr(
        users_service,
        "get_settings",
        lambda: SimpleNamespace(upload_dir=tmp_path, max_upload_size_bytes=1024),
    )
    alice, _bob, _charlie, group = await _make_group(client)
    conversation_id = group["id"]

    first = await client.put(
        f"/conversations/{conversation_id}/avatar",
        headers=auth_headers(alice["access_token"]),
        files={"file": ("first.png", PNG_BYTES, "image/png")},
    )
    assert first.status_code == 200, first.text
    first_path = tmp_path / "avatars" / first.json()["avatar_url"].rsplit("/", 1)[-1].split("?")[0]
    assert first_path.exists()

    second = await client.put(
        f"/conversations/{conversation_id}/avatar",
        headers=auth_headers(alice["access_token"]),
        files={"file": ("second.png", PNG_BYTES, "image/png")},
    )
    assert second.status_code == 200, second.text
    second_path = tmp_path / "avatars" / second.json()["avatar_url"].rsplit("/", 1)[-1].split("?")[0]
    assert second_path.exists()
    assert not first_path.exists()
