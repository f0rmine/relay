from pathlib import Path
from uuid import uuid4

import aiofiles
from fastapi import HTTPException, UploadFile, status
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.attachment import Attachment
from app.models.user import User

ALLOWED_AVATAR_TYPES = {"image/jpeg", "image/png", "image/webp", "image/gif"}
ALLOWED_AVATAR_EXTENSIONS = {
    "image/jpeg": {".jpg", ".jpeg"},
    "image/png": {".png"},
    "image/webp": {".webp"},
    "image/gif": {".gif"},
}


def placeholder_avatar(username: str) -> str:
    return f"https://api.dicebear.com/8.x/initials/svg?seed={username}"


async def search_users(db: AsyncSession, q: str, current_user_id: str, limit: int = 20) -> list[User]:
    term = f"%{q.lower()}%"
    stmt = (
        select(User)
        .where(User.id != current_user_id)
        .where(
            or_(
                User.username.ilike(term),
                User.display_name.ilike(term),
                User.email.ilike(term),
            )
        )
        .order_by(User.username.asc())
        .limit(limit)
    )
    return list((await db.scalars(stmt)).all())


async def save_avatar(db: AsyncSession, user: User, file: UploadFile) -> User:
    settings = get_settings()
    suffix = Path(file.filename or "").suffix.lower()
    data = await file.read()
    if not data:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Empty avatar upload")
    if file.content_type not in ALLOWED_AVATAR_TYPES:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Unsupported avatar image type")
    if suffix not in ALLOWED_AVATAR_EXTENSIONS[file.content_type]:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Avatar extension does not match file type")

    sniffed_type: str | None = None
    if data.startswith(b"\xff\xd8\xff"):
        sniffed_type = "image/jpeg"
    elif data.startswith(b"\x89PNG\r\n\x1a\n"):
        sniffed_type = "image/png"
    elif data.startswith(b"GIF87a") or data.startswith(b"GIF89a"):
        sniffed_type = "image/gif"
    elif len(data) > 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        sniffed_type = "image/webp"

    if sniffed_type != file.content_type:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Avatar content does not match file type")
    if len(data) > settings.max_upload_size_bytes:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "Avatar is too large")

    stored_filename = f"{uuid4()}{suffix}"
    avatar_dir = settings.upload_dir / "avatars"
    avatar_dir.mkdir(parents=True, exist_ok=True)
    path = avatar_dir / stored_filename
    async with aiofiles.open(path, "wb") as out:
        await out.write(data)
    user.avatar_url = f"/uploads/avatars/{stored_filename}"
    await db.commit()
    await db.refresh(user)
    return user
