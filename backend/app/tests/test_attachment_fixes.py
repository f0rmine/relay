from httpx import AsyncClient

from app.tests.conftest import register


def auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def make_png(size: tuple[int, int] = (8, 8)) -> bytes:
    from io import BytesIO

    from PIL import Image

    buffer = BytesIO()
    Image.new("RGB", size, (10, 20, 30)).save(buffer, format="PNG")
    return buffer.getvalue()


async def test_voice_note_upload_accepted(client: AsyncClient) -> None:
    alice = await register(client, "alice", "alice@example.com")

    webm = await client.post(
        "/attachments/upload",
        headers=auth_headers(alice["access_token"]),
        files={"file": ("voice-123.webm", b"fake-opus-bytes", "audio/webm;codecs=opus")},
    )
    assert webm.status_code == 201, webm.text
    assert webm.json()["mime_type"] == "audio/webm"

    m4a = await client.post(
        "/attachments/upload",
        headers=auth_headers(alice["access_token"]),
        files={"file": ("voice-456.m4a", b"fake-m4a-bytes", "audio/mp4")},
    )
    assert m4a.status_code == 201, m4a.text
    assert m4a.json()["mime_type"] == "audio/mp4"


async def test_thumb_download_decrypts(client: AsyncClient) -> None:
    alice = await register(client, "alice", "alice@example.com")
    png = make_png()

    uploaded = await client.post(
        "/attachments/upload",
        headers=auth_headers(alice["access_token"]),
        files={"file": ("photo.png", png, "image/png")},
    )
    assert uploaded.status_code == 201, uploaded.text
    body = uploaded.json()
    assert body["thumb_w"] is not None and body["thumb_h"] is not None
    attachment_id = body["id"]

    full = await client.get(
        f"/attachments/{attachment_id}/download",
        headers=auth_headers(alice["access_token"]),
    )
    assert full.status_code == 200, full.text
    assert full.content == png
    assert full.headers["content-type"] == "image/png"
    assert "inline" in full.headers["content-disposition"]

    thumb = await client.get(
        f"/attachments/{attachment_id}/download?variant=thumb",
        headers=auth_headers(alice["access_token"]),
    )
    assert thumb.status_code == 200, thumb.text
    assert thumb.content.startswith(b"\xff\xd8\xff")  # JPEG thumbnail
    assert thumb.headers["content-type"] == "image/jpeg"


async def test_gif_thumb_variant_falls_back_to_full_mime(client: AsyncClient) -> None:
    alice = await register(client, "alice", "alice@example.com")
    gif = b"GIF89a" + b"\x01\x00\x01\x00\x80\x00\x00\x00\x00\x00\x00\x00\x00" + b"\x21\xf9\x04\x01\x00\x00\x00\x00" + b"\x2c\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02\x02\x44\x01\x00\x3b"

    uploaded = await client.post(
        "/attachments/upload",
        headers=auth_headers(alice["access_token"]),
        files={"file": ("anim.gif", gif, "image/gif")},
    )
    assert uploaded.status_code == 201, uploaded.text
    attachment_id = uploaded.json()["id"]
    assert uploaded.json()["thumb_w"] is None

    thumb = await client.get(
        f"/attachments/{attachment_id}/download?variant=thumb",
        headers=auth_headers(alice["access_token"]),
    )
    assert thumb.status_code == 200, thumb.text
    assert thumb.content == gif
    assert thumb.headers["content-type"] == "image/gif"


async def test_media_download_is_inline_and_supports_range(client: AsyncClient) -> None:
    alice = await register(client, "alice", "alice@example.com")

    uploaded = await client.post(
        "/attachments/upload",
        headers=auth_headers(alice["access_token"]),
        files={"file": ("voice-789.webm", b"0123456789abcdef", "audio/webm")},
    )
    assert uploaded.status_code == 201, uploaded.text
    attachment_id = uploaded.json()["id"]

    ranged = await client.get(
        f"/attachments/{attachment_id}/download",
        headers={**auth_headers(alice["access_token"]), "Range": "bytes=4-9"},
    )
    assert ranged.status_code == 206, ranged.text
    assert ranged.content == b"456789"
    assert ranged.headers["content-range"] == "bytes 4-9/16"
    assert ranged.headers["accept-ranges"] == "bytes"
    assert "inline" in ranged.headers["content-disposition"]

    bad = await client.get(
        f"/attachments/{attachment_id}/download",
        headers={**auth_headers(alice["access_token"]), "Range": "bytes=999-1000"},
    )
    assert bad.status_code == 416

    text = await client.post(
        "/attachments/upload",
        headers=auth_headers(alice["access_token"]),
        files={"file": ("note.txt", b"hello world", "text/plain")},
    )
    assert text.status_code == 201
    text_id = text.json()["id"]
    inline = await client.get(
        f"/attachments/{text_id}/download", headers=auth_headers(alice["access_token"])
    )
    assert "inline" in inline.headers["content-disposition"]

    docx = await client.post(
        "/attachments/upload",
        headers=auth_headers(alice["access_token"]),
        files={
            "file": (
                "doc.docx",
                b"fake-docx",
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            )
        },
    )
    assert docx.status_code == 201
    docx_id = docx.json()["id"]
    attached = await client.get(
        f"/attachments/{docx_id}/download", headers=auth_headers(alice["access_token"])
    )
    assert "attachment" in attached.headers["content-disposition"]
