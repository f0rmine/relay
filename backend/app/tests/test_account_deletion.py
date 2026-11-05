import pytest
from httpx import AsyncClient

from app.tests.conftest import register


def _auth_headers(tokens: dict) -> dict[str, str]:
    return {"Authorization": f"Bearer {tokens['access_token']}"}


@pytest.mark.asyncio
async def test_account_deletion_full_flow(client: AsyncClient) -> None:
    victim = await register(client, "victim_user", "victim@example.com")
    other = await register(client, "other_user", "other@example.com")

    headers = _auth_headers(victim)
    refresh_token = victim["refresh_token"]

    # Wrong confirmation -> 422
    bad = await client.request(
        "DELETE", "/auth/account", headers=headers, json={"confirmation": "NOPE"}
    )
    assert bad.status_code == 422, bad.text

    # Delete works
    deleted = await client.request(
        "DELETE", "/auth/account", headers=headers, json={"confirmation": "DELETE"}
    )
    assert deleted.status_code == 204, deleted.text

    # Login after delete fails (generic invalid credentials)
    login = await client.post(
        "/auth/login", json={"login": "victim_user", "password": "password123"}
    )
    assert login.status_code == 401, login.text
    assert login.json()["detail"] == "Invalid credentials"

    # Old access token rejected
    me = await client.get("/auth/me", headers=headers)
    assert me.status_code == 401, me.text

    # Old refresh token rejected (sessions revoked)
    refresh = await client.post("/auth/refresh", json={"refresh_token": refresh_token})
    assert refresh.status_code == 401, refresh.text

    # Search excludes deleted user
    results = await client.get(
        "/users/search", params={"q": "victim"}, headers=_auth_headers(other)
    )
    assert results.status_code == 200, results.text
    usernames = [u["username"] for u in results.json()]
    assert "victim_user" not in usernames

    # Old username/email can be re-registered (tombstone suffix freed them)
    again = await client.post(
        "/auth/register",
        json={
            "username": "victim_user",
            "display_name": "New Victim",
            "email": "victim@example.com",
            "password": "password123",
        },
    )
    assert again.status_code == 201, again.text


@pytest.mark.asyncio
async def test_deleted_user_shown_as_deleted_user_in_conversation(
    client: AsyncClient,
) -> None:
    victim = await register(client, "conv_victim", "conv_victim@example.com")
    other = await register(client, "conv_other", "conv_other@example.com")
    other_headers = _auth_headers(other)

    created = await client.post(
        "/conversations",
        headers=other_headers,
        json={"participant_id": victim["user"]["id"]},
    )
    assert created.status_code in {200, 201}, created.text
    conversation_id = created.json()["id"]

    deleted = await client.request(
        "DELETE",
        "/auth/account",
        headers=_auth_headers(victim),
        json={"confirmation": "DELETE"},
    )
    assert deleted.status_code == 204, deleted.text

    fetched = await client.get(
        f"/conversations/{conversation_id}", headers=other_headers
    )
    assert fetched.status_code == 200, fetched.text
    participants = fetched.json()["participants"]
    victim_participant = next(
        (p for p in participants if p["id"] == victim["user"]["id"]), None
    )
    assert victim_participant is not None
    assert victim_participant["display_name"] == "Deleted User"
    assert victim_participant["is_online"] is False
