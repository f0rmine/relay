from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

from httpx import AsyncClient
from sqlalchemy import update

from app.tests.conftest import register


def auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def test_video_upload_ok(client: AsyncClient) -> None:
    alice = await register(client, "alice", "alice@example.com")
    for filename, mime in [
        ("clip.mp4", "video/mp4"),
        ("clip.mov", "video/quicktime"),
        ("clip.webm", "video/webm"),
    ]:
        uploaded = await client.post(
            "/attachments/upload",
            headers=auth_headers(alice["access_token"]),
            files={"file": (filename, b"\x00\x00\x00\x18ftypmp42payload", mime)},
        )
        assert uploaded.status_code == 201, (filename, uploaded.text)
        assert uploaded.json()["mime_type"] == mime
        assert uploaded.json()["original_filename"] == filename


async def test_video_extension_mismatch_rejected(client: AsyncClient) -> None:
    alice = await register(client, "alice", "alice@example.com")
    mismatched = await client.post(
        "/attachments/upload",
        headers=auth_headers(alice["access_token"]),
        files={"file": ("clip.mp4", b"payload", "video/webm")},
    )
    assert mismatched.status_code == 400

    wrong_ext = await client.post(
        "/attachments/upload",
        headers=auth_headers(alice["access_token"]),
        files={"file": ("clip.txt", b"payload", "video/mp4")},
    )
    assert wrong_ext.status_code == 400


async def test_video_over_limit_rejected(client: AsyncClient, monkeypatch, tmp_path) -> None:
    from app.services import attachments as attachment_service

    alice = await register(client, "alice", "alice@example.com")
    monkeypatch.setattr(
        attachment_service,
        "get_settings",
        lambda: SimpleNamespace(
            upload_dir=tmp_path,
            max_upload_size_bytes=1024,
            max_video_size_bytes=4,
            upload_daily_size_limit_mb=1024,
        ),
    )
    too_large = await client.post(
        "/attachments/upload",
        headers=auth_headers(alice["access_token"]),
        files={"file": ("clip.mp4", b"12345 payload over video limit", "video/mp4")},
    )
    assert too_large.status_code == 413

    # A small video under the (patched) limit still passes, and images
    # remain governed by the separate image/doc limit.
    small_video = await client.post(
        "/attachments/upload",
        headers=auth_headers(alice["access_token"]),
        files={"file": ("clip.mp4", b"1234", "video/mp4")},
    )
    assert small_video.status_code == 201, small_video.text


async def test_video_config_default() -> None:
    from app.core.config import Settings

    settings = Settings()
    assert settings.max_video_size_mb == 100
    assert settings.max_video_size_bytes == 100 * 1024 * 1024
    assert settings.max_upload_size_bytes == 10 * 1024 * 1024


async def test_first_unread_id_and_clears_after_read(client: AsyncClient) -> None:
    from app.core.database import get_db
    from app.main import app
    from app.models.message import Message
    from app.models.user import User
    from app.services.messages import create_message

    alice = await register(client, "alice", "alice@example.com")
    bob = await register(client, "bob", "bob@example.com")
    created = await client.post(
        "/conversations",
        json={"participant_id": bob["user"]["id"]},
        headers=auth_headers(alice["access_token"]),
    )
    conversation_id = created.json()["id"]

    override = app.dependency_overrides[get_db]
    async for db in override():
        bob_user = await db.get(User, bob["user"]["id"])
        first = await create_message(db, bob_user, conversation_id, "first", [])
        second = await create_message(db, bob_user, conversation_id, "second", [])
        base = datetime(2026, 1, 1, tzinfo=UTC)
        await db.execute(
            update(Message).where(Message.id == first.id).values(created_at=base)
        )
        await db.execute(
            update(Message)
            .where(Message.id == second.id)
            .values(created_at=base + timedelta(seconds=1))
        )
        await db.commit()
        break

    response = await client.get("/conversations", headers=auth_headers(alice["access_token"]))
    assert response.status_code == 200
    by_id = {c["id"]: c for c in response.json()}
    assert by_id[conversation_id]["unread_count"] == 2
    assert by_id[conversation_id]["first_unread_id"] == first.id

    # Single-conversation view agrees
    detail = await client.get(
        f"/conversations/{conversation_id}", headers=auth_headers(alice["access_token"])
    )
    assert detail.json()["first_unread_id"] == first.id

    # Sender sees no unread divider for their own messages
    sender_view = await client.get("/conversations", headers=auth_headers(bob["access_token"]))
    sender_by_id = {c["id"]: c for c in sender_view.json()}
    assert sender_by_id[conversation_id]["unread_count"] == 0
    assert sender_by_id[conversation_id]["first_unread_id"] is None

    read = await client.post(
        f"/conversations/{conversation_id}/read", headers=auth_headers(alice["access_token"])
    )
    assert read.status_code == 200

    after = await client.get("/conversations", headers=auth_headers(alice["access_token"]))
    after_by_id = {c["id"]: c for c in after.json()}
    assert after_by_id[conversation_id]["unread_count"] == 0
    assert after_by_id[conversation_id]["first_unread_id"] is None


async def test_first_unread_id_none_without_messages(client: AsyncClient) -> None:
    alice = await register(client, "alice", "alice@example.com")
    bob = await register(client, "bob", "bob@example.com")
    created = await client.post(
        "/conversations",
        json={"participant_id": bob["user"]["id"]},
        headers=auth_headers(alice["access_token"]),
    )
    assert created.json()["first_unread_id"] is None
    assert created.json()["unread_count"] == 0
