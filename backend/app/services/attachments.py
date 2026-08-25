from contextlib import suppress
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import aiofiles
from fastapi import HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import AsyncSessionLocal
from app.core.encryption import (
    ENCRYPTION_VERSION,
    DecryptionError,
    attachment_associated_data,
    get_encryption_keyring,
)
from app.core.redis import get_redis
from app.models.attachment import Attachment
from app.models.conversation import ConversationParticipant
from app.models.message import Message
from app.models.user import User
from app.services.uploads import read_upload_limited

MAX_ORIGINAL_FILENAME_LENGTH = 255

ALLOWED_MIME_TYPES = {
    "image/jpeg",
    "image/png",
    "image/webp",
    "image/gif",
    "application/pdf",
    "text/plain",
    "application/msword",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}

ALLOWED_EXTENSIONS_BY_MIME_TYPE = {
    "image/jpeg": {".jpg", ".jpeg"},
    "image/png": {".png"},
    "image/webp": {".webp"},
    "image/gif": {".gif"},
    "application/pdf": {".pdf"},
    "text/plain": {".txt"},
    "application/msword": {".doc"},
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": {".docx"},
}


THUMB_MAX_DIMENSION = 320


def attachment_thumb_associated_data(attachment_id: str) -> bytes:
    return f"relay:attachment:{attachment_id}:thumb:v1".encode()


def generate_thumbnail(data: bytes, mime_type: str) -> tuple[bytes, int, int] | None:
    if not is_image(mime_type) or mime_type == "image/gif":
        return None
    try:
        from io import BytesIO

        from PIL import Image

        with Image.open(BytesIO(data)) as image:
            image = image.convert("RGB") if image.mode not in ("RGB", "L") else image
            image.thumbnail((THUMB_MAX_DIMENSION, THUMB_MAX_DIMENSION))
            buffer = BytesIO()
            image.save(buffer, format="JPEG", quality=80)
            thumb_bytes = buffer.getvalue()
            return thumb_bytes, image.width, image.height
    except Exception:  # noqa: BLE001
        return None


def is_image(mime_type: str) -> bool:
    return mime_type.startswith("image/")


def sniff_image_type(data: bytes) -> str | None:
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data.startswith((b"GIF87a", b"GIF89a")):
        return "image/gif"
    if len(data) > 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return None


def normalized_filename(filename: str | None) -> str:
    name = (filename or "upload").replace("\\", "/").rsplit("/", 1)[-1].strip()
    if not name:
        name = "upload"
    if len(name) > MAX_ORIGINAL_FILENAME_LENGTH:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Filename is too long")
    if any(ord(character) < 32 or ord(character) == 127 for character in name):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Filename contains invalid characters")
    return name


async def _ensure_daily_upload_quota(user: User, size_bytes: int) -> None:
    settings = get_settings()
    day = datetime.now(UTC).strftime("%Y%m%d")
    key = f"quota:uploads:{user.id}:{day}"
    redis = await get_redis()
    used = int(await redis.incrby(key, size_bytes))
    if used == size_bytes:
        await redis.expire(key, 60 * 60 * 25)
    if used > settings.upload_daily_size_limit_mb * 1024 * 1024:
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Upload quota exceeded")


async def save_upload(db: AsyncSession, user: User, file: UploadFile) -> Attachment:
    settings = get_settings()
    original_filename = normalized_filename(file.filename)
    content_type = (file.content_type or "").split(";", 1)[0].strip().lower()
    if content_type not in ALLOWED_MIME_TYPES:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Unsupported file type")
    suffix = Path(original_filename).suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS_BY_MIME_TYPE[content_type]:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "File extension does not match file type")

    data = await read_upload_limited(file, settings.max_upload_size_bytes)
    if not data:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Empty file upload")
    if is_image(content_type) and sniff_image_type(data) != content_type:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Image content does not match file type")
    await _ensure_daily_upload_quota(user, len(data))

    attachment_id = str(uuid4())
    encrypted_data = get_encryption_keyring().encrypt(
        data,
        associated_data=attachment_associated_data(attachment_id),
    )
    stored_filename = f"{uuid4()}.enc"
    upload_dir = settings.upload_dir / "attachments"
    upload_dir.mkdir(parents=True, exist_ok=True)
    path = upload_dir / stored_filename
    thumb_info = generate_thumbnail(data, content_type)
    thumb_path: Path | None = None
    if thumb_info is not None:
        thumb_bytes, thumb_w, thumb_h = thumb_info
        encrypted_thumb = get_encryption_keyring().encrypt(
            thumb_bytes,
            associated_data=attachment_thumb_associated_data(attachment_id),
        )
        stored_thumb = f"{uuid4()}.enc"
        thumb_path = upload_dir / stored_thumb
    else:
        encrypted_thumb = None
        thumb_w = thumb_h = None

    attachment = Attachment(
        id=attachment_id,
        uploader_id=user.id,
        original_filename=original_filename,
        stored_filename=stored_filename,
        mime_type=content_type,
        file_size=len(data),
        storage_path=str(path),
        encrypted_path=str(path),
        public_url=f"/attachments/{attachment_id}/download",
        encryption_nonce=encrypted_data.nonce,
        encryption_key_id=encrypted_data.key_id,
        encryption_version=encrypted_data.version,
    )
    if thumb_path is not None and encrypted_thumb is not None and thumb_w and thumb_h:
        attachment.thumb_path = str(thumb_path)
        attachment.thumb_size = len(thumb_bytes)
        attachment.thumb_w = thumb_w
        attachment.thumb_h = thumb_h
    try:
        async with aiofiles.open(path, "wb") as out:
            await out.write(encrypted_data.ciphertext)
        if thumb_path is not None and encrypted_thumb is not None:
            async with aiofiles.open(thumb_path, "wb") as out:
                await out.write(encrypted_thumb.ciphertext)
        db.add(attachment)
        await db.commit()
    except Exception:
        await db.rollback()
        with suppress(FileNotFoundError):
            path.unlink()
        if thumb_path is not None:
            with suppress(FileNotFoundError):
                thumb_path.unlink()
        raise
    await db.refresh(attachment)
    return attachment


async def read_attachment_bytes(
    attachment: Attachment, variant: str = "full"
) -> bytes:
    use_thumb = variant == "thumb" and attachment.thumb_path is not None
    path = Path(
        attachment.thumb_path if use_thumb else (attachment.encrypted_path or attachment.storage_path)
    )
    if not path.exists():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "File missing from storage")
    async with aiofiles.open(path, "rb") as stored_file:
        stored_data = await stored_file.read()
    encryption_metadata = (
        attachment.encryption_nonce,
        attachment.encryption_key_id,
        attachment.encryption_version,
        attachment.encrypted_path,
    )
    aad = (
        attachment_thumb_associated_data(attachment.id)
        if use_thumb
        else attachment_associated_data(attachment.id)
    )
    if all(value is None for value in encryption_metadata):
        return stored_data
    if any(value is None for value in encryption_metadata):
        raise DecryptionError("Encrypted attachment metadata is incomplete")
    if attachment.encryption_version != ENCRYPTION_VERSION:
        raise DecryptionError("Unsupported attachment encryption version")
    return get_encryption_keyring().decrypt(
        stored_data,
        attachment.encryption_nonce,
        attachment.encryption_key_id,
        associated_data=aad,
    )


async def require_attachment_access(
    db: AsyncSession, attachment_id: str, user_id: str
) -> Attachment:
    attachment = await db.get(Attachment, attachment_id)
    if attachment is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Attachment not found")
    if attachment.uploader_id == user_id and attachment.message_id is None:
        return attachment
    if attachment.message_id is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Attachment not found")

    message = await db.get(Message, attachment.message_id)
    if message is None or message.deleted_at is not None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Attachment not found")
    participant = await db.scalar(
        select(ConversationParticipant.id).where(
            ConversationParticipant.conversation_id == message.conversation_id,
            ConversationParticipant.user_id == user_id,
        )
    )
    if participant is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Attachment not found")
    return attachment


async def cleanup_orphan_attachments() -> int:
    settings = get_settings()
    cutoff = datetime.now(UTC) - timedelta(hours=settings.orphan_attachment_ttl_hours)
    async with AsyncSessionLocal() as db:
        orphans = (
            await db.scalars(
                select(Attachment).where(
                    Attachment.message_id.is_(None),
                    Attachment.created_at < cutoff,
                )
            )
        ).all()
        for attachment in orphans:
            with suppress(OSError):
                Path(attachment.encrypted_path or attachment.storage_path).unlink(missing_ok=True)
            await db.delete(attachment)
        await db.commit()
        return len(orphans)
