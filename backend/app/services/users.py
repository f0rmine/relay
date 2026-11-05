import logging
from contextlib import suppress
from pathlib import Path
from uuid import uuid4

import aiofiles
from fastapi import HTTPException, UploadFile, status
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.auth import PasswordResetToken, RefreshToken
from app.models.device import DeviceToken
from app.models.user import User
from app.models.user_device import UserDevice
from app.services.attachments import sniff_image_type
from app.services.uploads import read_upload_limited

logger = logging.getLogger(__name__)
ALLOWED_AVATAR_TYPES = {"image/jpeg", "image/png", "image/webp", "image/gif"}
ALLOWED_AVATAR_EXTENSIONS = {
    "image/jpeg": {".jpg", ".jpeg"},
    "image/png": {".png"},
    "image/webp": {".webp"},
    "image/gif": {".gif"},
}
AVATAR_URL_PREFIX = "/uploads/avatars/"


async def search_users(db: AsyncSession, q: str, current_user_id: str, limit: int = 20) -> list[User]:
    from app.services.blocks import blocked_ids_union

    escaped = q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    term = f"%{escaped.lower()}%"
    excluded = await blocked_ids_union(db, current_user_id)
    stmt = (
        select(User)
        .where(User.id != current_user_id)
        .where(User.deleted_at.is_(None))
        .where(
            or_(
                User.username.ilike(term, escape="\\"),
                User.display_name.ilike(term, escape="\\"),
            )
        )
        .order_by(User.username.asc())
        .limit(limit)
    )
    if excluded:
        stmt = stmt.where(~User.id.in_(excluded))
    return list((await db.scalars(stmt)).all())


async def validate_image_upload(
    file: UploadFile, max_bytes: int | None = None
) -> tuple[bytes, str, str]:
    """Validate an avatar image upload.

    Returns ``(data, content_type, suffix)``. Raises 400/413 on invalid input.
    """
    settings = get_settings()
    limit = max_bytes if max_bytes is not None else settings.max_upload_size_bytes
    filename = (file.filename or "").replace("\\", "/").rsplit("/", 1)[-1]
    suffix = Path(filename).suffix.lower()
    data = await read_upload_limited(
        file, limit, too_large_detail="Avatar is too large"
    )
    if not data:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Empty avatar upload")
    content_type = (file.content_type or "").split(";", 1)[0].strip().lower()
    if content_type not in ALLOWED_AVATAR_TYPES:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Unsupported avatar image type")
    if suffix not in ALLOWED_AVATAR_EXTENSIONS[content_type]:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Avatar extension does not match file type")
    if sniff_image_type(data) != content_type:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Avatar content does not match file type")
    return data, content_type, suffix


async def store_avatar_file(data: bytes, suffix: str) -> tuple[Path, str]:
    """Write image bytes to the shared avatars dir; return (path, avatar_url)."""
    settings = get_settings()
    stored_filename = f"{uuid4()}{suffix}"
    avatar_dir = settings.upload_dir / "avatars"
    avatar_dir.mkdir(parents=True, exist_ok=True)
    path = avatar_dir / stored_filename
    async with aiofiles.open(path, "wb") as out:
        await out.write(data)
    return path, f"{AVATAR_URL_PREFIX}{stored_filename}"


def remove_previous_avatar_file(previous_avatar_url: str | None, keep_path: Path | None = None) -> None:
    if not previous_avatar_url or not previous_avatar_url.startswith(AVATAR_URL_PREFIX):
        return
    settings = get_settings()
    avatar_dir = settings.upload_dir / "avatars"
    previous_path = avatar_dir / Path(previous_avatar_url).name
    if keep_path is not None and previous_path == keep_path:
        return
    try:
        previous_path.unlink(missing_ok=True)
    except OSError:
        logger.warning("Unable to remove replaced avatar file", exc_info=True)


async def save_avatar(db: AsyncSession, user: User, file: UploadFile) -> User:
    data, _content_type, suffix = await validate_image_upload(file)
    path, new_url = await store_avatar_file(data, suffix)
    previous_avatar_url = user.avatar_url
    user.avatar_url = new_url
    try:
        await db.commit()
    except Exception:
        await db.rollback()
        with suppress(FileNotFoundError):
            path.unlink()
        raise

    remove_previous_avatar_file(previous_avatar_url, keep_path=path)
    await db.refresh(user)
    return user


async def delete_user_account(db: AsyncSession, user: User) -> User:
    """Soft-tombstone the account while retaining messages for chat integrity."""
    from datetime import UTC, datetime

    from sqlalchemy import delete

    from app.models.recovery_code import RecoveryCode
    from app.services.auth import revoke_all_access_tokens

    now = datetime.now(UTC)
    suffix = f"_del_{uuid4().hex[:8]}"
    old_username = user.username or "user"
    old_email = user.email or "user@example.com"
    avatar_url = user.avatar_url

    user.deleted_at = now
    user.username = (old_username[: 32 - len(suffix)] + suffix)[:32]
    user.email = (old_email[: 255 - len(suffix)] + suffix)[:255]
    user.display_name = "Deleted User"
    user.avatar_url = None
    user.totp_secret_ciphertext = None
    user.totp_enabled = False

    await db.execute(
        delete(UserDevice).where(UserDevice.user_id == user.id)
    )
    await db.execute(delete(RecoveryCode).where(RecoveryCode.user_id == user.id))

    refresh_rows = (
        await db.scalars(
            select(RefreshToken).where(
                RefreshToken.user_id == user.id, RefreshToken.revoked_at.is_(None)
            )
        )
    ).all()
    for row in refresh_rows:
        row.revoked_at = now

    reset_rows = (
        await db.scalars(
            select(PasswordResetToken).where(
                PasswordResetToken.user_id == user.id,
                PasswordResetToken.used_at.is_(None),
            )
        )
    ).all()
    for row in reset_rows:
        row.used_at = now

    device_rows = (
        await db.scalars(select(DeviceToken).where(DeviceToken.user_id == user.id))
    ).all()
    for row in device_rows:
        row.enabled = False

    await db.commit()
    await db.refresh(user)

    if avatar_url:
        remove_previous_avatar_file(avatar_url)

    try:
        await revoke_all_access_tokens(user.id)
    except Exception:
        logger.warning("Failed to revoke access tokens on account deletion", exc_info=True)

    try:
        from app.core.redis import get_redis

        redis = await get_redis()
        await redis.delete(f"presence:user:{user.id}")
    except Exception:
        logger.warning("Failed to clear presence on account deletion", exc_info=True)

    return user
