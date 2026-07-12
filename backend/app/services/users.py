import logging
from contextlib import suppress
from pathlib import Path
from uuid import uuid4

import aiofiles
from fastapi import HTTPException, UploadFile, status
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.user import User
from app.services.uploads import read_upload_limited

logger = logging.getLogger(__name__)
ALLOWED_AVATAR_TYPES = {"image/jpeg", "image/png", "image/webp", "image/gif"}
ALLOWED_AVATAR_EXTENSIONS = {
    "image/jpeg": {".jpg", ".jpeg"},
    "image/png": {".png"},
    "image/webp": {".webp"},
    "image/gif": {".gif"},
}


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
    filename = (file.filename or "").replace("\\", "/").rsplit("/", 1)[-1]
    suffix = Path(filename).suffix.lower()
    data = await read_upload_limited(
        file, settings.max_upload_size_bytes, too_large_detail="Avatar is too large"
    )
    if not data:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Empty avatar upload")
    content_type = (file.content_type or "").split(";", 1)[0].strip().lower()
    if content_type not in ALLOWED_AVATAR_TYPES:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Unsupported avatar image type")
    if suffix not in ALLOWED_AVATAR_EXTENSIONS[content_type]:
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

    if sniffed_type != content_type:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Avatar content does not match file type")

    stored_filename = f"{uuid4()}{suffix}"
    avatar_dir = settings.upload_dir / "avatars"
    avatar_dir.mkdir(parents=True, exist_ok=True)
    path = avatar_dir / stored_filename
    previous_avatar_url = user.avatar_url
    user.avatar_url = f"/uploads/avatars/{stored_filename}"
    try:
        async with aiofiles.open(path, "wb") as out:
            await out.write(data)
        await db.commit()
    except Exception:
        await db.rollback()
        with suppress(FileNotFoundError):
            path.unlink()
        raise

    if previous_avatar_url and previous_avatar_url.startswith("/uploads/avatars/"):
        previous_path = avatar_dir / Path(previous_avatar_url).name
        if previous_path != path:
            try:
                previous_path.unlink(missing_ok=True)
            except OSError:
                logger.warning("Unable to remove replaced avatar file", exc_info=True)
    await db.refresh(user)
    return user
