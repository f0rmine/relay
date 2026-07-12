import json
from datetime import UTC, datetime, timedelta
from contextlib import asynccontextmanager
from types import SimpleNamespace

import httpx

from httpx import AsyncClient
from sqlalchemy import select, update

from app.tests.conftest import register


def auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def test_register_login_and_protected_me(client: AsyncClient) -> None:
    tokens = await register(client, "alice", "alice@example.com")
    assert tokens["user"]["username"] == "alice"
    assert tokens["user"]["avatar_url"] is None
    assert "password_hash" not in tokens["user"]

    login = await client.post(
        "/auth/login", json={"login": "alice@example.com", "password": "password123"}
    )
    assert login.status_code == 200
    me = await client.get("/auth/me", headers=auth_headers(login.json()["access_token"]))
    assert me.status_code == 200
    assert me.json()["email"] == "alice@example.com"


async def test_register_trims_and_rejects_blank_display_name(client: AsyncClient) -> None:
    trimmed = await client.post(
        "/auth/register",
        json={
            "username": "alice",
            "display_name": "  Alice Example  ",
            "email": "alice@example.com",
            "password": "password123",
        },
    )
    assert trimmed.status_code == 201, trimmed.text
    assert trimmed.json()["user"]["display_name"] == "Alice Example"

    blank = await client.post(
        "/auth/register",
        json={
            "username": "bob",
            "display_name": "   ",
            "email": "bob@example.com",
            "password": "password123",
        },
    )
    assert blank.status_code == 422


async def test_validation_errors_do_not_echo_sensitive_input(client: AsyncClient) -> None:
    password = "short7"
    response = await client.post(
        "/auth/register",
        json={
            "username": "alice",
            "display_name": "Alice",
            "email": "alice@example.com",
            "password": password,
        },
    )

    assert response.status_code == 422
    assert password not in response.text
    assert all("input" not in error for error in response.json()["detail"])


async def test_refresh_token_rotation_rejects_reuse(client: AsyncClient) -> None:
    tokens = await register(client, "alice", "alice@example.com")

    refreshed = await client.post(
        "/auth/refresh",
        json={"refresh_token": tokens["refresh_token"]},
    )
    assert refreshed.status_code == 200

    reused = await client.post(
        "/auth/refresh",
        json={"refresh_token": tokens["refresh_token"]},
    )
    assert reused.status_code == 401

    second_refresh = await client.post(
        "/auth/refresh",
        json={"refresh_token": refreshed.json()["refresh_token"]},
    )
    assert second_refresh.status_code == 200


async def test_refresh_token_uses_jti_and_supports_legacy_rows(client: AsyncClient) -> None:
    from app.core.database import get_db
    from app.core.security import decode_jwt_token
    from app.main import app
    from app.models.auth import RefreshToken

    tokens = await register(client, "alice", "alice@example.com")
    payload = decode_jwt_token(tokens["refresh_token"], "refresh")

    override = app.dependency_overrides[get_db]
    async for db in override():
        token_row = (
            await db.scalars(select(RefreshToken).where(RefreshToken.jti == payload["jti"]))
        ).first()
        assert token_row is not None
        await db.execute(
            RefreshToken.__table__.update()
            .where(RefreshToken.jti == payload["jti"])
            .values(jti=None)
        )
        await db.commit()
        break

    refreshed = await client.post(
        "/auth/refresh",
        json={"refresh_token": tokens["refresh_token"]},
    )

    assert refreshed.status_code == 200
    assert decode_jwt_token(refreshed.json()["refresh_token"], "refresh")["jti"]


async def test_password_reset_revokes_refresh_sessions_and_reset_tokens(
    client: AsyncClient,
) -> None:
    tokens = await register(client, "alice", "alice@example.com")

    first_reset = await client.post("/auth/forgot-password", json={"email": "alice@example.com"})
    second_reset = await client.post("/auth/forgot-password", json={"email": "alice@example.com"})
    assert first_reset.status_code == 200
    assert second_reset.status_code == 200
    first_token = first_reset.json()["reset_token"]
    second_token = second_reset.json()["reset_token"]

    reset = await client.post(
        "/auth/reset-password",
        json={"token": first_token, "new_password": "newpassword123"},
    )
    assert reset.status_code == 204

    old_login = await client.post(
        "/auth/login", json={"login": "alice", "password": "password123"}
    )
    assert old_login.status_code == 401
    new_login = await client.post(
        "/auth/login", json={"login": "alice", "password": "newpassword123"}
    )
    assert new_login.status_code == 200

    reused_reset = await client.post(
        "/auth/reset-password",
        json={"token": second_token, "new_password": "anotherpassword123"},
    )
    assert reused_reset.status_code == 400

    reused_refresh = await client.post(
        "/auth/refresh",
        json={"refresh_token": tokens["refresh_token"]},
    )
    assert reused_refresh.status_code == 401


async def test_password_reset_token_is_hidden_without_explicit_debug_setting(
    client: AsyncClient, monkeypatch
) -> None:
    from types import SimpleNamespace

    from app.api.routes import auth as auth_route

    await register(client, "alice", "alice@example.com")
    monkeypatch.setattr(
        auth_route,
        "get_settings",
        lambda: SimpleNamespace(password_reset_token_in_response=False),
    )

    response = await client.post("/auth/forgot-password", json={"email": "alice@example.com"})

    assert response.status_code == 200
    assert response.json()["reset_token"] is None


async def test_user_search_excludes_current_user(client: AsyncClient) -> None:
    alice = await register(client, "alice", "alice@example.com")
    await register(client, "bob", "bob@example.com")

    response = await client.get("/users/search?q=bob", headers=auth_headers(alice["access_token"]))
    assert response.status_code == 200
    users = response.json()
    assert len(users) == 1
    assert users[0]["username"] == "bob"


async def test_profile_update_rejects_duplicate_email(client: AsyncClient) -> None:
    alice = await register(client, "alice", "alice@example.com")
    await register(client, "bob", "bob@example.com")

    renamed = await client.patch(
        "/users/me/profile",
        headers=auth_headers(alice["access_token"]),
        json={"display_name": "  Alice Updated  "},
    )
    assert renamed.status_code == 200
    assert renamed.json()["display_name"] == "Alice Updated"

    blank_name = await client.patch(
        "/users/me/profile",
        headers=auth_headers(alice["access_token"]),
        json={"display_name": "   "},
    )
    assert blank_name.status_code == 422

    response = await client.patch(
        "/users/me/profile",
        headers=auth_headers(alice["access_token"]),
        json={"email": "bob@example.com"},
    )

    assert response.status_code == 409


async def test_avatar_upload_validation(client: AsyncClient) -> None:
    alice = await register(client, "alice", "alice@example.com")

    empty = await client.post(
        "/users/me/avatar",
        headers=auth_headers(alice["access_token"]),
        files={"file": ("avatar.png", b"", "image/png")},
    )
    assert empty.status_code == 400

    spoofed_extension = await client.post(
        "/users/me/avatar",
        headers=auth_headers(alice["access_token"]),
        files={"file": ("avatar.sh", b"\x89PNG\r\n\x1a\npayload", "image/png")},
    )
    assert spoofed_extension.status_code == 400

    spoofed_content = await client.post(
        "/users/me/avatar",
        headers=auth_headers(alice["access_token"]),
        files={"file": ("avatar.png", b"not really png", "image/png")},
    )
    assert spoofed_content.status_code == 400

    valid = await client.post(
        "/users/me/avatar",
        headers=auth_headers(alice["access_token"]),
        files={"file": ("avatar.png", b"\x89PNG\r\n\x1a\npayload", "image/png")},
    )
    assert valid.status_code == 200
    assert valid.json()["avatar_url"].startswith("/uploads/avatars/")


async def test_replacing_avatar_removes_previous_local_file(
    client: AsyncClient, monkeypatch, tmp_path
) -> None:
    from app.services import users as users_service

    monkeypatch.setattr(
        users_service,
        "get_settings",
        lambda: SimpleNamespace(upload_dir=tmp_path, max_upload_size_bytes=1024),
    )
    alice = await register(client, "alice", "alice@example.com")
    image = b"\x89PNG\r\n\x1a\npayload"

    first = await client.post(
        "/users/me/avatar",
        headers=auth_headers(alice["access_token"]),
        files={"file": ("first.png", image, "image/png")},
    )
    first_path = tmp_path / "avatars" / first.json()["avatar_url"].rsplit("/", 1)[-1]
    assert first_path.exists()

    second = await client.post(
        "/users/me/avatar",
        headers=auth_headers(alice["access_token"]),
        files={"file": ("second.png", image, "image/png")},
    )
    second_path = tmp_path / "avatars" / second.json()["avatar_url"].rsplit("/", 1)[-1]

    assert second.status_code == 200
    assert second_path.exists()
    assert not first_path.exists()


async def test_private_conversation_message_read_and_delete(client: AsyncClient, monkeypatch) -> None:
    alice = await register(client, "alice", "alice@example.com")
    bob = await register(client, "bob", "bob@example.com")
    charlie = await register(client, "charlie", "charlie@example.com")

    create = await client.post(
        "/conversations",
        json={"participant_id": bob["user"]["id"]},
        headers=auth_headers(alice["access_token"]),
    )
    assert create.status_code == 200, create.text
    conversation_id = create.json()["id"]

    duplicate_create = await client.post(
        "/conversations",
        json={"participant_id": bob["user"]["id"]},
        headers=auth_headers(alice["access_token"]),
    )
    assert duplicate_create.status_code == 200, duplicate_create.text
    assert duplicate_create.json()["id"] == conversation_id

    uploaded = await client.post(
        "/attachments/upload",
        headers=auth_headers(alice["access_token"]),
        files={"file": ("note.txt", b"hello", "text/plain")},
    )
    assert uploaded.status_code == 201, uploaded.text
    attachment_id = uploaded.json()["id"]
    assert uploaded.json()["public_url"] == f"/attachments/{attachment_id}/download"
    anonymous_download = await client.get(f"/attachments/{attachment_id}/download")
    assert anonymous_download.status_code == 401

    # Use the service-level path that WebSocket calls for persistence.
    from app.core.database import get_db
    from app.main import app
    from app.models.attachment import Attachment
    from app.models.message import Message
    from app.models.user import User
    from app.services.messages import create_message

    override = app.dependency_overrides[get_db]
    async for db in override():
        user = await db.get(User, alice["user"]["id"])
        message = await create_message(db, user, conversation_id, "hello bob", [attachment_id])
        attachment = await db.get(Attachment, attachment_id)
        stored_filename = attachment.stored_filename
        stored_path = attachment.storage_path
        assert message.text is None
        assert message.text_ciphertext is not None
        assert b"hello bob" not in message.text_ciphertext
        assert message.text_nonce is not None
        assert message.text_key_id == "test-v1"
        assert message.encryption_version == 1
        assert attachment.encryption_nonce is not None
        assert attachment.encryption_key_id == "test-v1"
        assert attachment.encryption_version == 1
        assert attachment.encrypted_path == attachment.storage_path
        assert attachment.stored_filename.endswith(".enc")
        message_id = message.id
        break

    with open(stored_path, "rb") as stored_file:
        assert stored_file.read() != b"hello"

    public_static_file = await client.get(f"/uploads/attachments/{stored_filename}")
    assert public_static_file.status_code == 404

    allowed_attachment = await client.get(
        f"/attachments/{attachment_id}", headers=auth_headers(bob["access_token"])
    )
    assert allowed_attachment.status_code == 200
    allowed_download = await client.get(
        f"/attachments/{attachment_id}/download", headers=auth_headers(bob["access_token"])
    )
    assert allowed_download.status_code == 200
    assert allowed_download.content == b"hello"
    rejected_attachment = await client.get(
        f"/attachments/{attachment_id}", headers=auth_headers(charlie["access_token"])
    )
    assert rejected_attachment.status_code == 404

    from app.api.routes import attachments as attachments_route

    async def fail_if_decryption_is_attempted(attachment) -> bytes:
        raise AssertionError("unauthorized attachment reached decryption")

    monkeypatch.setattr(attachments_route, "read_attachment_bytes", fail_if_decryption_is_attempted)
    rejected_download = await client.get(
        f"/attachments/{attachment_id}/download",
        headers=auth_headers(charlie["access_token"]),
    )
    assert rejected_download.status_code == 404

    history = await client.get(
        f"/conversations/{conversation_id}/messages", headers=auth_headers(bob["access_token"])
    )
    assert history.status_code == 200
    assert history.json()["items"][0]["text"] == "hello bob"
    assert history.json()["items"][0]["attachments"][0]["id"] == attachment_id
    assert history.json()["items"][0]["attachments"][0]["public_url"] == f"/attachments/{attachment_id}/download"

    from app.websocket import events as websocket_events

    def fail_if_message_decryption_is_attempted(message) -> str:
        raise AssertionError("unauthorized message reached decryption")

    with monkeypatch.context() as authorization_check:
        authorization_check.setattr(
            websocket_events,
            "plaintext_message_text",
            fail_if_message_decryption_is_attempted,
        )
        rejected_history = await client.get(
            f"/conversations/{conversation_id}/messages",
            headers=auth_headers(charlie["access_token"]),
        )
    assert rejected_history.status_code == 404

    from app.api.routes import conversations as conversations_route
    from app.api.routes import messages as messages_route

    broadcasts: list[tuple[list[str], str, dict]] = []

    async def fake_broadcast(redis, user_ids: list[str], event_type: str, payload: dict) -> None:
        broadcasts.append((user_ids, event_type, payload))

    monkeypatch.setattr(conversations_route.manager, "broadcast_to_users", fake_broadcast)
    monkeypatch.setattr(messages_route.manager, "broadcast_to_users", fake_broadcast)

    read = await client.post(
        f"/conversations/{conversation_id}/read", headers=auth_headers(bob["access_token"])
    )
    assert read.status_code == 200
    assert message_id in read.json()["message_ids"]
    assert broadcasts[-1][1] == "message:read"
    assert broadcasts[-1][2]["conversation_id"] == conversation_id
    assert broadcasts[-1][2]["user_id"] == bob["user"]["id"]
    assert message_id in broadcasts[-1][2]["message_ids"]

    deleted = await client.delete(
        f"/messages/{message_id}", headers=auth_headers(alice["access_token"])
    )
    assert deleted.status_code == 200
    assert deleted.json()["deleted_at"] is not None
    assert deleted.json()["text"] is None
    assert deleted.json()["attachments"] == []
    assert [event for _, event, _ in broadcasts[-2:]] == ["message:deleted", "conversation:updated"]
    assert broadcasts[-2][2]["id"] == message_id
    assert broadcasts[-2][2]["deleted_at"] is not None
    assert broadcasts[-1][2]["latest_message"]["id"] == message_id

    async for db in override():
        deleted_message = await db.get(Message, message_id)
        assert deleted_message.text is None
        assert deleted_message.text_ciphertext is None
        assert deleted_message.text_nonce is None
        assert deleted_message.text_key_id is None
        assert deleted_message.encryption_version is None
        break

    hidden_attachment = await client.get(
        f"/attachments/{attachment_id}", headers=auth_headers(bob["access_token"])
    )
    assert hidden_attachment.status_code == 404

    deleted_history = await client.get(
        f"/conversations/{conversation_id}/messages", headers=auth_headers(bob["access_token"])
    )
    assert deleted_history.json()["items"][0]["attachments"] == []


async def test_message_history_pagination_returns_next_cursor(client: AsyncClient) -> None:
    alice = await register(client, "alice", "alice@example.com")
    bob = await register(client, "bob", "bob@example.com")

    created = await client.post(
        "/conversations",
        json={"participant_id": bob["user"]["id"]},
        headers=auth_headers(alice["access_token"]),
    )
    conversation_id = created.json()["id"]

    from app.core.database import get_db
    from app.main import app
    from app.models.user import User
    from app.services.messages import create_message

    override = app.dependency_overrides[get_db]
    async for db in override():
        sender = await db.get(User, alice["user"]["id"])
        for text in ["first", "second", "third"]:
            await create_message(db, sender, conversation_id, text, [])
        break

    page = await client.get(
        f"/conversations/{conversation_id}/messages?limit=2",
        headers=auth_headers(bob["access_token"]),
    )

    assert page.status_code == 200, page.text
    body = page.json()
    assert len(body["items"]) == 2
    assert body["has_more"] is True
    assert body["next_cursor"] is not None


async def test_conversation_list_batches_latest_messages_and_unread_counts(
    client: AsyncClient,
) -> None:
    from app.core.database import get_db
    from app.main import app
    from app.models.user import User
    from app.services.messages import create_message

    alice = await register(client, "alice", "alice@example.com")
    bob = await register(client, "bob", "bob@example.com")
    charlie = await register(client, "charlie", "charlie@example.com")
    bob_conversation = await client.post(
        "/conversations",
        json={"participant_id": bob["user"]["id"]},
        headers=auth_headers(alice["access_token"]),
    )
    charlie_conversation = await client.post(
        "/conversations",
        json={"participant_id": charlie["user"]["id"]},
        headers=auth_headers(alice["access_token"]),
    )

    override = app.dependency_overrides[get_db]
    async for db in override():
        bob_user = await db.get(User, bob["user"]["id"])
        charlie_user = await db.get(User, charlie["user"]["id"])
        await create_message(db, bob_user, bob_conversation.json()["id"], "bob first", [])
        await create_message(db, bob_user, bob_conversation.json()["id"], "bob latest", [])
        await create_message(
            db, charlie_user, charlie_conversation.json()["id"], "charlie latest", []
        )
        break

    response = await client.get(
        "/conversations", headers=auth_headers(alice["access_token"])
    )

    assert response.status_code == 200
    by_id = {conversation["id"]: conversation for conversation in response.json()}
    assert by_id[bob_conversation.json()["id"]]["latest_message"]["text"] == "bob latest"
    assert by_id[bob_conversation.json()["id"]]["unread_count"] == 2
    assert (
        by_id[charlie_conversation.json()["id"]]["latest_message"]["text"]
        == "charlie latest"
    )
    assert by_id[charlie_conversation.json()["id"]]["unread_count"] == 1


async def test_repeated_read_only_creates_receipts_for_new_messages(client: AsyncClient) -> None:
    from app.core.database import get_db
    from app.main import app
    from app.models.message import MessageRead
    from app.models.user import User
    from app.services.messages import create_message

    alice = await register(client, "alice", "alice@example.com")
    bob = await register(client, "bob", "bob@example.com")
    conversation = await client.post(
        "/conversations",
        json={"participant_id": bob["user"]["id"]},
        headers=auth_headers(alice["access_token"]),
    )
    conversation_id = conversation.json()["id"]

    override = app.dependency_overrides[get_db]
    async for db in override():
        sender = await db.get(User, alice["user"]["id"])
        first_message = await create_message(db, sender, conversation_id, "first", [])
        break

    first_read = await client.post(
        f"/conversations/{conversation_id}/read",
        headers=auth_headers(bob["access_token"]),
    )
    repeated_read = await client.post(
        f"/conversations/{conversation_id}/read",
        headers=auth_headers(bob["access_token"]),
    )
    assert first_read.json()["message_ids"] == [first_message.id]
    assert repeated_read.json()["message_ids"] == []

    async for db in override():
        sender = await db.get(User, alice["user"]["id"])
        second_message = await create_message(db, sender, conversation_id, "second", [])
        break

    second_read = await client.post(
        f"/conversations/{conversation_id}/read",
        headers=auth_headers(bob["access_token"]),
    )
    assert second_read.json()["message_ids"] == [second_message.id]

    async for db in override():
        receipts = list(
            (
                await db.scalars(
                    select(MessageRead).where(MessageRead.user_id == bob["user"]["id"])
                )
            ).all()
        )
        assert {receipt.message_id for receipt in receipts} == {
            first_message.id,
            second_message.id,
        }
        break


async def test_message_history_cursor_handles_equal_timestamps(client: AsyncClient) -> None:
    alice = await register(client, "alice", "alice@example.com")
    bob = await register(client, "bob", "bob@example.com")
    created = await client.post(
        "/conversations",
        json={"participant_id": bob["user"]["id"]},
        headers=auth_headers(alice["access_token"]),
    )
    conversation_id = created.json()["id"]

    from app.core.database import get_db
    from app.main import app
    from app.models.message import Message
    from app.models.user import User
    from app.services.messages import create_message

    override = app.dependency_overrides[get_db]
    async for db in override():
        sender = await db.get(User, alice["user"]["id"])
        for text in ["first", "second", "third"]:
            await create_message(db, sender, conversation_id, text, [])
        common_time = datetime(2026, 1, 1, tzinfo=UTC)
        await db.execute(
            update(Message)
            .where(Message.conversation_id == conversation_id)
            .values(created_at=common_time)
        )
        await db.commit()
        break

    first_page = await client.get(
        f"/conversations/{conversation_id}/messages?limit=2",
        headers=auth_headers(bob["access_token"]),
    )
    cursor = first_page.json()["next_cursor"]
    second_page = await client.get(
        f"/conversations/{conversation_id}/messages?limit=2&cursor={cursor}",
        headers=auth_headers(bob["access_token"]),
    )

    assert first_page.status_code == 200, first_page.text
    assert second_page.status_code == 200, second_page.text
    ids = [item["id"] for item in first_page.json()["items"] + second_page.json()["items"]]
    assert len(ids) == 3
    assert len(set(ids)) == 3


async def test_file_upload_validation(client: AsyncClient) -> None:
    alice = await register(client, "alice", "alice@example.com")
    rejected = await client.post(
        "/attachments/upload",
        headers=auth_headers(alice["access_token"]),
        files={"file": ("bad.sh", b"echo nope", "application/x-sh")},
    )
    assert rejected.status_code == 400

    spoofed = await client.post(
        "/attachments/upload",
        headers=auth_headers(alice["access_token"]),
        files={"file": ("bad.sh", b"echo nope", "text/plain")},
    )
    assert spoofed.status_code == 400

    spoofed_image = await client.post(
        "/attachments/upload",
        headers=auth_headers(alice["access_token"]),
        files={"file": ("image.png", b"not really png", "image/png")},
    )
    assert spoofed_image.status_code == 400

    accepted = await client.post(
        "/attachments/upload",
        headers=auth_headers(alice["access_token"]),
        files={"file": ("note.txt", b"hello", "text/plain")},
    )
    assert accepted.status_code == 201, accepted.text
    assert accepted.json()["original_filename"] == "note.txt"

    normalized = await client.post(
        "/attachments/upload",
        headers=auth_headers(alice["access_token"]),
        files={"file": ("../../safe.txt", b"hello", "text/plain")},
    )
    assert normalized.status_code == 201
    assert normalized.json()["original_filename"] == "safe.txt"

    too_long = await client.post(
        "/attachments/upload",
        headers=auth_headers(alice["access_token"]),
        files={"file": (f"{'a' * 252}.txt", b"hello", "text/plain")},
    )
    assert too_long.status_code == 400
    assert too_long.json()["detail"] == "Filename is too long"


async def test_failed_attachment_commit_removes_written_file(monkeypatch, tmp_path) -> None:
    from io import BytesIO

    import pytest
    from fastapi import UploadFile
    from starlette.datastructures import Headers

    from app.services import attachments as attachment_service

    class FailedDatabase:
        rolled_back = False

        def add(self, attachment) -> None:
            return None

        async def commit(self) -> None:
            raise RuntimeError("database unavailable")

        async def rollback(self) -> None:
            self.rolled_back = True

    database = FailedDatabase()
    monkeypatch.setattr(
        attachment_service,
        "get_settings",
        lambda: SimpleNamespace(upload_dir=tmp_path, max_upload_size_bytes=1024),
    )
    upload = UploadFile(
        filename="note.txt",
        file=BytesIO(b"hello"),
        headers=Headers({"content-type": "text/plain"}),
    )

    with pytest.raises(RuntimeError, match="database unavailable"):
        await attachment_service.save_upload(database, SimpleNamespace(id="user-1"), upload)

    assert database.rolled_back is True
    assert list((tmp_path / "attachments").iterdir()) == []


async def test_upload_reader_stops_above_limit() -> None:
    from io import BytesIO

    import pytest
    from fastapi import HTTPException, UploadFile

    from app.services.uploads import read_upload_limited

    upload = UploadFile(filename="large.txt", file=BytesIO(b"12345"))
    with pytest.raises(HTTPException) as raised:
        await read_upload_limited(upload, max_bytes=4)
    assert raised.value.status_code == 413


async def test_upload_with_invalid_conversation_does_not_create_orphan_attachment(
    client: AsyncClient,
) -> None:
    alice = await register(client, "alice", "alice@example.com")

    rejected = await client.post(
        "/attachments/upload",
        headers=auth_headers(alice["access_token"]),
        data={"conversation_id": "00000000-0000-0000-0000-000000000000"},
        files={"file": ("note.txt", b"hello", "text/plain")},
    )

    assert rejected.status_code == 404

    from app.core.database import get_db
    from app.main import app
    from app.models.attachment import Attachment

    override = app.dependency_overrides[get_db]
    async for db in override():
        assert (await db.scalars(select(Attachment))).first() is None
        break


async def test_upload_with_conversation_does_not_broadcast_orphan_attachment(
    client: AsyncClient,
) -> None:
    alice = await register(client, "alice", "alice@example.com")
    bob = await register(client, "bob", "bob@example.com")
    created = await client.post(
        "/conversations",
        json={"participant_id": bob["user"]["id"]},
        headers=auth_headers(alice["access_token"]),
    )
    conversation_id = created.json()["id"]

    from app.api.routes import attachments as attachments_route

    assert not hasattr(attachments_route, "manager")
    assert not hasattr(attachments_route, "get_redis")

    uploaded = await client.post(
        "/attachments/upload",
        headers=auth_headers(alice["access_token"]),
        data={"conversation_id": conversation_id},
        files={"file": ("note.txt", b"hello", "text/plain")},
    )

    assert uploaded.status_code == 201, uploaded.text


async def test_push_token_register_and_remove(client: AsyncClient) -> None:
    alice = await register(client, "alice", "alice@example.com")
    token = "fcm-token-" + ("x" * 40)

    registered = await client.post(
        "/devices/push-token",
        headers=auth_headers(alice["access_token"]),
        json={"token": token, "platform": "android", "locale": "uk"},
    )
    assert registered.status_code == 204

    from app.core.database import get_db
    from app.main import app
    from app.models.device import DeviceToken

    override = app.dependency_overrides[get_db]
    async for db in override():
        device = (await db.scalars(select(DeviceToken).where(DeviceToken.token == token))).first()
        assert device is not None
        assert device.user_id == alice["user"]["id"]
        assert device.enabled is True
        assert device.locale == "uk"
        break

    removed = await client.request(
        "DELETE",
        "/devices/push-token",
        headers=auth_headers(alice["access_token"]),
        json={"token": token},
    )
    assert removed.status_code == 204

    async for db in override():
        device = (await db.scalars(select(DeviceToken).where(DeviceToken.token == token))).first()
        assert device is not None
        assert device.enabled is False
        break


async def test_push_preview_and_disabled_delivery(client: AsyncClient, monkeypatch) -> None:
    alice = await register(client, "alice", "alice@example.com")
    bob = await register(client, "bob", "bob@example.com")
    token = "fcm-token-" + ("y" * 40)

    created = await client.post(
        "/conversations",
        json={"participant_id": bob["user"]["id"]},
        headers=auth_headers(alice["access_token"]),
    )
    conversation_id = created.json()["id"]
    await client.post(
        "/devices/push-token",
        headers=auth_headers(bob["access_token"]),
        json={"token": token, "platform": "android"},
    )

    from app.core.database import get_db
    from app.main import app
    from app.models.user import User
    from app.services.messages import create_message
    from app.services.push import push_preview, send_message_push

    called = False

    async def fake_access_token() -> str:
        nonlocal called
        called = True
        return "unused"

    monkeypatch.setattr("app.services.push._access_token", fake_access_token)

    override = app.dependency_overrides[get_db]
    async for db in override():
        sender = await db.get(User, alice["user"]["id"])
        message = await create_message(db, sender, conversation_id, "push text", [])
        assert push_preview(message) == "push text"
        assert push_preview(message, "uk") == "push text"
        image_message = SimpleNamespace(
            deleted_at=None,
            text_ciphertext=None,
            text=None,
            attachments=[SimpleNamespace(mime_type="image/png")],
        )
        assert push_preview(image_message, "en") == "Image"
        assert push_preview(image_message, "uk") == "Зображення"
        attachment_message = SimpleNamespace(
            deleted_at=None,
            text_ciphertext=None,
            text=None,
            attachments=[SimpleNamespace(mime_type="application/pdf")],
        )
        assert push_preview(attachment_message, "en") == "Attachment"
        assert push_preview(attachment_message, "uk") == "Вкладення"
        generic_message = SimpleNamespace(
            deleted_at=None,
            text_ciphertext=None,
            text=None,
            attachments=[],
        )
        assert push_preview(generic_message, "en") == "Message"
        assert push_preview(generic_message, "uk") == "Повідомлення"
        deleted_message = SimpleNamespace(deleted_at=True)
        assert push_preview(deleted_message, "en") == "Message deleted"
        assert push_preview(deleted_message, "uk") == "Повідомлення видалено"
        await send_message_push(db, [bob["user"]["id"]], sender, message)
        break

    assert called is False


async def test_fcm_error_summary_is_compact() -> None:
    from app.services.push import _fcm_error_summary

    response = httpx.Response(
        403,
        json={
            "error": {
                "status": "PERMISSION_DENIED",
                "message": "Permission 'cloudmessaging.messages.create' denied.",
            }
        },
    )

    assert (
        _fcm_error_summary(response)
        == "PERMISSION_DENIED: Permission 'cloudmessaging.messages.create' denied."
    )


async def test_fcm_permission_error_sets_cooldown(monkeypatch) -> None:
    from app.services import push

    monkeypatch.setattr(push, "_fcm_config_disabled_until", 0.0)
    response = httpx.Response(
        403,
        json={
            "error": {
                "status": "PERMISSION_DENIED",
                "message": "Permission 'cloudmessaging.messages.create' denied.",
            }
        },
    )

    summary = push._fcm_error_summary(response)

    assert push._mark_fcm_config_error(response, summary) is True
    assert push._fcm_config_error_active() is True

    monkeypatch.setattr(push, "_fcm_config_disabled_until", 0.0)


async def test_fcm_missing_service_account_path_skips_delivery(monkeypatch, tmp_path) -> None:
    from app.services import push

    called = False

    async def fake_access_token() -> str:
        nonlocal called
        called = True
        return "unused"

    monkeypatch.setattr(push, "_fcm_config_disabled_until", 0.0)
    monkeypatch.setattr(push, "_access_token", fake_access_token)
    monkeypatch.setattr(
        push,
        "get_settings",
        lambda: SimpleNamespace(
            push_notifications_enabled=True,
            firebase_project_id="relay-test",
            firebase_service_account_file=tmp_path / "missing.json",
        ),
    )

    await push.send_message_push(None, ["user-id"], None, None)  # type: ignore[arg-type]

    assert called is False
    assert push._fcm_config_error_active() is True
    monkeypatch.setattr(push, "_fcm_config_disabled_until", 0.0)


async def test_fcm_credential_error_is_push_only(monkeypatch, client: AsyncClient) -> None:
    from app.main import app
    from app.core.database import get_db
    from app.models.user import User
    from app.services import push
    from app.services.messages import create_message

    alice = await register(client, "alice", "alice@example.com")
    bob = await register(client, "bob", "bob@example.com")
    conversation = await client.post(
        "/conversations",
        headers=auth_headers(alice["access_token"]),
        json={"participant_id": bob["user"]["id"]},
    )
    assert conversation.status_code in {200, 201}
    token = await client.post(
        "/devices/push-token",
        headers=auth_headers(bob["access_token"]),
        json={"token": "bob-fcm-token-" + ("x" * 32), "platform": "android"},
    )
    assert token.status_code == 204

    async def broken_access_token() -> str:
        raise ValueError("bad credentials")

    monkeypatch.setattr(push, "_fcm_config_disabled_until", 0.0)
    monkeypatch.setattr(push, "_access_token", broken_access_token)
    monkeypatch.setattr(
        push,
        "get_settings",
        lambda: SimpleNamespace(
            push_notifications_enabled=True,
            firebase_project_id="relay-test",
            firebase_service_account_file=__file__,
        ),
    )

    override = app.dependency_overrides[get_db]
    async for db in override():
        sender = await db.get(User, alice["user"]["id"])
        message = await create_message(db, sender, conversation.json()["id"], "push text", [])
        await push.send_message_push(db, [bob["user"]["id"]], sender, message)
        break

    assert push._fcm_config_error_active() is True
    monkeypatch.setattr(push, "_fcm_config_disabled_until", 0.0)


async def test_websocket_auth_uses_first_frame_token() -> None:
    from app.core.security import create_jwt_token
    from app.models.user import User
    from app.websocket.routes import authenticate_websocket

    user = User(
        id="user-1",
        username="alice",
        email="alice@example.com",
        display_name="Alice",
        password_hash="hash",
    )
    token = create_jwt_token(user.id, "access", timedelta(minutes=1))

    class FakeDb:
        async def get(self, model, user_id: str):
            assert model is User
            return user if user_id == user.id else None

    class FakeWebSocket:
        async def receive_json(self) -> dict:
            return {"type": "auth", "payload": {"token": token}}

    authenticated = await authenticate_websocket(FakeDb(), FakeWebSocket())

    assert authenticated is user


async def test_websocket_connect_sends_auth_ok_before_events(client: AsyncClient, monkeypatch) -> None:
    alice = await register(client, "alice", "alice@example.com")

    from app.core.database import get_db
    from app.main import app
    from app.websocket import routes as websocket_routes

    class FakeRedis:
        async def publish(self, channel: str, value: str) -> int:
            return 0

    class FakeWebSocket:
        sent: list[dict]

        def __init__(self) -> None:
            self.sent = []
            self._received = False

        async def accept(self) -> None:
            return None

        async def receive_json(self) -> dict:
            if self._received is True:
                self._received = "malformed"
                raise json.JSONDecodeError("invalid", "{", 1)
            if self._received == "malformed":
                from fastapi import WebSocketDisconnect

                raise WebSocketDisconnect(code=1000)
            self._received = True
            return {"type": "auth", "payload": {"token": alice["access_token"]}}

        async def send_json(self, payload: dict) -> None:
            self.sent.append(payload)

        async def close(self, code: int) -> None:
            return None

    async def fake_get_redis() -> FakeRedis:
        return FakeRedis()

    async def fake_set_online(redis, user_id: str, instance_id: str) -> bool:
        return True

    async def fake_set_offline(redis, user_id: str, instance_id: str) -> bool:
        return False

    async def fake_peer_ids(db, user_id: str) -> list[str]:
        return []

    async def fake_broadcast(redis, user_ids: list[str], event_type: str, payload: dict) -> None:
        return None

    websocket = FakeWebSocket()
    monkeypatch.setattr(websocket_routes, "get_redis", fake_get_redis)
    monkeypatch.setattr(websocket_routes, "set_online", fake_set_online)
    monkeypatch.setattr(websocket_routes, "set_offline", fake_set_offline)
    monkeypatch.setattr(websocket_routes, "participant_ids_for_user", fake_peer_ids)
    monkeypatch.setattr(websocket_routes.manager, "broadcast_to_users", fake_broadcast)
    override = app.dependency_overrides[get_db]

    @asynccontextmanager
    async def fake_session_factory():
        async for db in override():
            yield db
            break

    monkeypatch.setattr(websocket_routes, "AsyncSessionLocal", fake_session_factory)

    await websocket_routes.websocket_endpoint(websocket)

    assert websocket.sent[0]["type"] == "auth:ok"
    assert websocket.sent[0]["payload"]["user_id"] == alice["user"]["id"]
    assert websocket.sent[1] == {"type": "error", "payload": {"detail": "Invalid JSON payload"}}


async def test_websocket_message_send_broadcasts_and_persists(client: AsyncClient, monkeypatch) -> None:
    alice = await register(client, "alice", "alice@example.com")
    bob = await register(client, "bob", "bob@example.com")

    created = await client.post(
        "/conversations",
        json={"participant_id": bob["user"]["id"]},
        headers=auth_headers(alice["access_token"]),
    )
    conversation_id = created.json()["id"]

    from app.core.database import get_db
    from app.main import app
    from app.models.message import Message
    from app.models.user import User
    from app.schemas.ws import WebSocketEnvelope
    from app.websocket import routes as websocket_routes

    sent_json: list[dict] = []
    broadcasts: list[tuple[list[str], str, dict]] = []
    push_calls: list[tuple[list[str], str, str]] = []

    class FakeWebSocket:
        async def send_json(self, payload: dict) -> None:
            sent_json.append(payload)

    async def fake_broadcast(redis, user_ids: list[str], event_type: str, payload: dict) -> None:
        broadcasts.append((user_ids, event_type, payload))

    def fake_schedule_push(recipient_ids: list[str], sender_id: str, message_id: str) -> None:
        push_calls.append((recipient_ids, sender_id, message_id))

    monkeypatch.setattr(websocket_routes.manager, "broadcast_to_users", fake_broadcast)
    monkeypatch.setattr(websocket_routes.manager, "is_connected", lambda user_id: False)
    monkeypatch.setattr(websocket_routes.manager, "is_in_room", lambda conversation_id, user_id: False)
    monkeypatch.setattr(websocket_routes, "schedule_message_push", fake_schedule_push)

    override = app.dependency_overrides[get_db]
    async for db in override():
        sender = await db.get(User, alice["user"]["id"])
        await websocket_routes.handle_event(
            db,
            redis=None,
            websocket=FakeWebSocket(),
            user=sender,
            envelope=WebSocketEnvelope(
                type="message:send",
                request_id="client-request-1",
                payload={
                    "conversation_id": conversation_id,
                    "text": "hello over ws",
                    "attachment_ids": [],
                },
            ),
        )
        persisted = (
            await db.scalars(select(Message).where(Message.conversation_id == conversation_id))
        ).first()
        break

    assert sent_json == []
    assert persisted is not None
    assert persisted.text is None
    assert b"hello over ws" not in persisted.text_ciphertext
    assert broadcasts[0][2]["text"] == "hello over ws"
    assert broadcasts[0][2]["request_id"] == "client-request-1"
    assert [event for _, event, _ in broadcasts] == ["message:new", "conversation:updated"]
    assert push_calls == [([bob["user"]["id"]], alice["user"]["id"], persisted.id)]


async def test_scheduled_push_runs_outside_message_handler_and_drains(monkeypatch) -> None:
    import asyncio

    from app.services import push

    started = asyncio.Event()
    release = asyncio.Event()
    calls: list[tuple[list[str], str, str]] = []

    async def delayed_push(recipient_ids: list[str], sender_id: str, message_id: str) -> None:
        calls.append((recipient_ids, sender_id, message_id))
        started.set()
        await release.wait()

    monkeypatch.setattr(push, "_send_message_push_by_id", delayed_push)

    push.schedule_message_push(["recipient"], "sender", "message")
    await started.wait()
    assert calls == [(["recipient"], "sender", "message")]

    release.set()
    await push.drain_push_tasks()


async def test_websocket_delete_updates_conversation_preview(client: AsyncClient, monkeypatch) -> None:
    alice = await register(client, "alice", "alice@example.com")
    bob = await register(client, "bob", "bob@example.com")

    created = await client.post(
        "/conversations",
        json={"participant_id": bob["user"]["id"]},
        headers=auth_headers(alice["access_token"]),
    )
    conversation_id = created.json()["id"]

    from app.core.database import get_db
    from app.main import app
    from app.models.user import User
    from app.schemas.ws import WebSocketEnvelope
    from app.services.messages import create_message
    from app.websocket import routes as websocket_routes

    broadcasts: list[tuple[list[str], str, dict]] = []

    class FakeWebSocket:
        async def send_json(self, payload: dict) -> None:
            raise AssertionError(f"unexpected direct send: {payload}")

    async def fake_broadcast(redis, user_ids: list[str], event_type: str, payload: dict) -> None:
        broadcasts.append((user_ids, event_type, payload))

    monkeypatch.setattr(websocket_routes.manager, "broadcast_to_users", fake_broadcast)

    override = app.dependency_overrides[get_db]
    async for db in override():
        sender = await db.get(User, alice["user"]["id"])
        message = await create_message(db, sender, conversation_id, "delete me", [])
        await websocket_routes.handle_event(
            db,
            redis=None,
            websocket=FakeWebSocket(),
            user=sender,
            envelope=WebSocketEnvelope(
                type="message:delete",
                payload={"message_id": message.id},
            ),
        )
        break

    assert [event for _, event, _ in broadcasts] == ["message:deleted", "conversation:updated"]
    latest = broadcasts[-1][2]["latest_message"]
    assert latest["id"] == message.id
    assert latest["deleted_at"] is not None
    assert latest["text"] is None


async def test_invalid_attachment_send_does_not_create_partial_message(client: AsyncClient) -> None:
    alice = await register(client, "alice", "alice@example.com")
    bob = await register(client, "bob", "bob@example.com")

    created = await client.post(
        "/conversations",
        json={"participant_id": bob["user"]["id"]},
        headers=auth_headers(alice["access_token"]),
    )
    conversation_id = created.json()["id"]

    from fastapi import HTTPException

    from app.core.database import get_db
    from app.main import app
    from app.models.message import Message
    from app.models.user import User
    from app.services.messages import create_message

    override = app.dependency_overrides[get_db]
    async for db in override():
        sender = await db.get(User, alice["user"]["id"])
        try:
            await create_message(db, sender, conversation_id, None, ["missing-attachment"])
        except HTTPException as error:
            assert error.status_code == 400
        else:
            raise AssertionError("Invalid attachment should reject the message")

        partial = (
            await db.scalars(select(Message).where(Message.conversation_id == conversation_id))
        ).first()
        assert partial is None
        break


async def test_connection_manager_removes_stale_websocket() -> None:
    from fastapi import WebSocketDisconnect

    from app.websocket.manager import ConnectionManager

    class StaleWebSocket:
        async def send_json(self, payload: dict) -> None:
            raise WebSocketDisconnect(code=1006)

    class FakeRedis:
        async def publish(self, channel: str, value: str) -> int:
            return 0

    manager = ConnectionManager()
    websocket = StaleWebSocket()
    manager.user_connections["user-1"].add(websocket)

    await manager.broadcast_to_users(FakeRedis(), ["user-1"], "message:new", {"id": "message-1"})

    assert "user-1" not in manager.user_connections


async def test_connection_manager_keeps_local_delivery_when_redis_publish_fails() -> None:
    from app.websocket.manager import ConnectionManager

    delivered: list[dict] = []

    class LocalWebSocket:
        async def send_json(self, payload: dict) -> None:
            delivered.append(payload)

    class FailedRedis:
        async def publish(self, channel: str, value: str) -> int:
            raise ConnectionError("redis unavailable")

    manager = ConnectionManager()
    manager.user_connections["user-1"].add(LocalWebSocket())

    await manager.broadcast_to_users(
        FailedRedis(), ["user-1"], "message:new", {"id": "message-1"}
    )

    assert delivered == [{"type": "message:new", "payload": {"id": "message-1"}}]


async def test_readiness_checks_database_redis_and_subscriber(client: AsyncClient, monkeypatch) -> None:
    from app import main as main_module

    class FakeSession:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, traceback) -> None:
            return None

        async def execute(self, statement) -> None:
            return None

    class RunningTask:
        def done(self) -> bool:
            return False

    async def healthy_redis() -> None:
        return None

    monkeypatch.setattr(main_module, "AsyncSessionLocal", FakeSession)
    monkeypatch.setattr(main_module, "ping_redis", healthy_redis)
    main_module.app.state.redis_subscriber_task = RunningTask()

    response = await client.get("/health/ready")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "checks": {"database": True, "redis": True, "subscriber": True},
    }


async def test_readiness_returns_503_without_dependencies(client: AsyncClient, monkeypatch) -> None:
    from app import main as main_module

    class FailedSession:
        async def __aenter__(self):
            raise ConnectionError("database unavailable")

        async def __aexit__(self, exc_type, exc, traceback) -> None:
            return None

    class StoppedTask:
        def done(self) -> bool:
            return True

    async def failed_redis() -> None:
        raise ConnectionError("redis unavailable")

    monkeypatch.setattr(main_module, "AsyncSessionLocal", FailedSession)
    monkeypatch.setattr(main_module, "ping_redis", failed_redis)
    main_module.app.state.redis_subscriber_task = StoppedTask()

    response = await client.get("/health/ready")

    assert response.status_code == 503
    assert response.json() == {
        "status": "not_ready",
        "checks": {"database": False, "redis": False, "subscriber": False},
    }
