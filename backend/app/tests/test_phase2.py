import io
import json
import zipfile
from datetime import UTC, datetime, timedelta

from httpx import AsyncClient

from app.tests.conftest import register


def auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}

PNG_BYTES = b"\x89PNG\r\n\x1a\npayload"


async def _make_chat(client: AsyncClient):
    alice = await register(client, "alice", "alice@example.com")
    bob = await register(client, "bob", "bob@example.com")
    created = await client.post(
        "/conversations",
        json={"participant_id": bob["user"]["id"]},
        headers=auth_headers(alice["access_token"]),
    )
    assert created.status_code == 200, created.text
    return alice, bob, created.json()["id"]


async def test_link_preview_private_ip_blocked(client: AsyncClient) -> None:
    alice, _bob, _conversation_id = await _make_chat(client)
    from app.services import link_previews as preview_service

    # SSRF guard blocks loopback literals without any network fetch.
    assert await preview_service._validate_public_url("http://127.0.0.1/secret") is False
    assert await preview_service._validate_public_url("http://169.254.169.254/metadata") is False
    assert await preview_service._fetch_html("http://127.0.0.1/secret") is None

    from app.core.database import get_db
    from app.main import app

    override = app.dependency_overrides[get_db]
    async for db in override():
        result = await preview_service.get_or_fetch_preview(db, "http://127.0.0.1/secret")
        assert result is None
        break

    # Route returns null preview for blocked URL.
    response = await client.get(
        "/link-previews",
        params={"url": "http://127.0.0.1/secret"},
        headers=auth_headers(alice["access_token"]),
    )
    assert response.status_code == 200, response.text
    assert response.json()["title"] is None


async def test_link_preview_public_fetch_mocked(client: AsyncClient, monkeypatch) -> None:
    alice, _bob, _conversation_id = await _make_chat(client)
    from app.services import link_previews as preview_service

    html = (
        "<html><head><title>Fallback</title>"
        '<meta property="og:title" content="OG Title">'
        '<meta property="og:description" content="OG Desc">'
        '<meta property="og:image" content="https://example.com/img.png">'
        "</head><body>hi</body></html>"
    )

    async def fake_fetch(url: str):
        return html

    monkeypatch.setattr(preview_service, "_fetch_html", fake_fetch)

    from app.core.database import get_db
    from app.main import app

    override = app.dependency_overrides[get_db]
    async for db in override():
        preview = await preview_service.get_or_fetch_preview(db, "https://example.com/page")
        assert preview is not None
        assert preview.title == "OG Title"
        assert preview.description == "OG Desc"
        assert preview.image_url == "https://example.com/img.png"
        # Cached on second call.
        cached = await preview_service.get_or_fetch_preview(db, "https://example.com/page")
        assert cached is not None and cached.id == preview.id
        break

    response = await client.get(
        "/link-previews",
        params={"url": "https://example.com/page"},
        headers=auth_headers(alice["access_token"]),
    )
    assert response.status_code == 200, response.text
    assert response.json()["title"] == "OG Title"

    # URL extraction from message text.
    assert preview_service.extract_first_url("check https://example.com/page now") == "https://example.com/page"
    assert preview_service.extract_first_url("no url here") is None


async def test_media_gallery_type_filter(client: AsyncClient) -> None:
    alice, bob, conversation_id = await _make_chat(client)
    from app.core.database import get_db
    from app.main import app
    from app.models.user import User
    from app.services.messages import create_message

    image = await client.post(
        "/attachments/upload",
        headers=auth_headers(alice["access_token"]),
        files={"file": ("pic.png", PNG_BYTES, "image/png")},
    )
    assert image.status_code == 201, image.text
    video = await client.post(
        "/attachments/upload",
        headers=auth_headers(alice["access_token"]),
        files={"file": ("clip.mp4", b"\x00\x00\x00\x18ftypmp42payload", "video/mp4")},
    )
    assert video.status_code == 201, video.text
    doc = await client.post(
        "/attachments/upload",
        headers=auth_headers(alice["access_token"]),
        files={"file": ("note.txt", b"hello", "text/plain")},
    )
    assert doc.status_code == 201, doc.text
    audio = await client.post(
        "/attachments/upload",
        headers=auth_headers(alice["access_token"]),
        files={"file": ("voice.m4a", b"audio-bytes", "audio/mp4")},
    )
    assert audio.status_code == 201, audio.text

    override = app.dependency_overrides[get_db]
    async for db in override():
        sender = await db.get(User, alice["user"]["id"])
        await create_message(db, sender, conversation_id, "image msg", [image.json()["id"]])
        await create_message(db, sender, conversation_id, "video msg", [video.json()["id"]])
        await create_message(db, sender, conversation_id, "doc msg", [doc.json()["id"]])
        await create_message(db, sender, conversation_id, "audio msg", [audio.json()["id"]])
        await create_message(db, sender, conversation_id, "plain text", [])
        break

    async def texts_for(media_type: str):
        response = await client.get(
            f"/conversations/{conversation_id}/messages?type={media_type}",
            headers=auth_headers(bob["access_token"]),
        )
        assert response.status_code == 200, response.text
        return sorted(item["text"] for item in response.json()["items"])

    assert await texts_for("media") == ["image msg", "video msg"]
    assert await texts_for("files") == ["doc msg"]
    assert await texts_for("audio") == ["audio msg"]


async def test_export_zip_and_gc(client: AsyncClient, monkeypatch, tmp_path) -> None:
    alice, _bob, conversation_id = await _make_chat(client)
    from app.core.database import get_db
    from app.main import app
    from app.models.export_job import ExportJob
    from app.models.user import User
    from app.services import exports as exports_service
    from app.services.messages import create_message

    def _export_dir():
        (tmp_path / "exports").mkdir(parents=True, exist_ok=True)
        return tmp_path / "exports"

    monkeypatch.setattr(exports_service, "exports_dir", _export_dir)

    override = app.dependency_overrides[get_db]
    async for db in override():
        sender = await db.get(User, alice["user"]["id"])
        await create_message(db, sender, conversation_id, "export me", [])
        await create_message(db, sender, conversation_id, "second", [])
        break

    # Create via REST (triggers immediate processing with request db).
    created = await client.post(
        "/exports",
        headers=auth_headers(alice["access_token"]),
        json={"conversation_id": conversation_id},
    )
    assert created.status_code == 201, created.text
    job_id = created.json()["id"]

    status_response = await client.get(
        f"/exports/{job_id}", headers=auth_headers(alice["access_token"])
    )
    assert status_response.status_code == 200
    assert status_response.json()["status"] == "done", status_response.text
    assert status_response.json()["file_path"]

    download = await client.get(
        f"/exports/{job_id}/download", headers=auth_headers(alice["access_token"])
    )
    assert download.status_code == 200, download.text
    archive = zipfile.ZipFile(io.BytesIO(download.content))
    names = archive.namelist()
    assert "messages.json" in names
    records = json.loads(archive.read("messages.json").decode("utf-8"))
    texts = [r["text"] for r in records]
    assert "export me" in texts
    assert "second" in texts

    # GC removes old finished jobs and their files.
    override = app.dependency_overrides[get_db]
    async for db in override():
        job = await db.get(ExportJob, job_id)
        assert job is not None
        job.finished_at = datetime.now(UTC) - timedelta(hours=25)
        await db.commit()
        removed = await exports_service.cleanup_old_exports(db)
        assert removed == 1
        assert await db.get(ExportJob, job_id) is None
        break
    assert not (tmp_path / "exports" / f"{job_id}.zip").exists()


async def test_export_owner_only_and_participant_check(client: AsyncClient, monkeypatch, tmp_path) -> None:
    alice, _bob, conversation_id = await _make_chat(client)
    charlie = await register(client, "charlie", "charlie@example.com")
    from app.core.database import get_db
    from app.main import app
    from app.models.user import User
    from app.services import exports as exports_service
    from app.services.messages import create_message

    def _export_dir2():
        (tmp_path / "exports").mkdir(parents=True, exist_ok=True)
        return tmp_path / "exports"

    monkeypatch.setattr(exports_service, "exports_dir", _export_dir2)

    override = app.dependency_overrides[get_db]
    async for db in override():
        sender = await db.get(User, alice["user"]["id"])
        await create_message(db, sender, conversation_id, "locked", [])
        break

    created = await client.post(
        "/exports",
        headers=auth_headers(alice["access_token"]),
        json={"conversation_id": conversation_id},
    )
    assert created.status_code == 201, created.text
    job_id = created.json()["id"]

    # Non-owner cannot view.
    other = await client.get(f"/exports/{job_id}", headers=auth_headers(charlie["access_token"]))
    assert other.status_code == 404

    # Non-participant cannot create export.
    rejected = await client.post(
        "/exports",
        headers=auth_headers(charlie["access_token"]),
        json={"conversation_id": conversation_id},
    )
    assert rejected.status_code == 404


async def test_scheduled_hidden_from_search(client: AsyncClient, monkeypatch) -> None:
    alice, bob, conversation_id = await _make_chat(client)
    from app.core.database import get_db
    from app.main import app
    from app.models.user import User
    from app.services.messages import create_message

    future = datetime.now(UTC) + timedelta(hours=3)
    override = app.dependency_overrides[get_db]
    async for db in override():
        sender = await db.get(User, alice["user"]["id"])
        await create_message(db, sender, conversation_id, "secretneedle", [], scheduled_at=future)
        break

    search = await client.get(
        "/search/messages?q=secretneedle", headers=auth_headers(bob["access_token"])
    )
    assert search.status_code == 200, search.text
    assert search.json() == []
