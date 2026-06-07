from pathlib import Path
from uuid import uuid4

import aiofiles
from fastapi import HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.attachment import Attachment
from app.models.conversation import ConversationParticipant
from app.models.message import Message
from app.models.user import User

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


def is_image(mime_type: str) -> bool:
    return mime_type.startswith("image/")


def sniff_image_type(data: bytes) -> str | None:
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data.startswith(b"GIF87a") or data.startswith(b"GIF89a"):
        return "image/gif"
    if len(data) > 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return None


async def save_upload(db: AsyncSession, user: User, file: UploadFile) -> Attachment:
    settings = get_settings()
    content_type = file.content_type
    if content_type not in ALLOWED_MIME_TYPES:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Unsupported file type")
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS_BY_MIME_TYPE[content_type]:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "File extension does not match file type")

    data = await file.read()
    if not data:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Empty file upload")
    if len(data) > settings.max_upload_size_bytes:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "File is too large")
    if is_image(content_type) and sniff_image_type(data) != content_type:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Image content does not match file type")

    attachment_id = str(uuid4())
    stored_filename = f"{uuid4()}{suffix}"
    upload_dir = settings.upload_dir / "attachments"
    upload_dir.mkdir(parents=True, exist_ok=True)
    path = upload_dir / stored_filename
    async with aiofiles.open(path, "wb") as out:
        await out.write(data)

    attachment = Attachment(
        id=attachment_id,
        uploader_id=user.id,
        original_filename=file.filename or "upload",
        stored_filename=stored_filename,
        mime_type=content_type,
        file_size=len(data),
        storage_path=str(path),
        public_url=f"/attachments/{attachment_id}/download",
    )
    db.add(attachment)
    await db.commit()
    await db.refresh(attachment)
    return attachment


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
