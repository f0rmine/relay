import mimetypes
import time
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, File, HTTPException, Query, UploadFile, status
from fastapi.responses import FileResponse, Response
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.api.deps import CurrentUser, DbSession
from app.core.config import get_settings
from app.core.redis import get_redis
from app.core.security import verify_avatar_url
from app.models.user import User
from app.models.user_block import UserBlock
from app.schemas.auth import AccountDeleteRequest
from app.schemas.user import ProfileUpdate, UserPublic, UserSearchResult
from app.services.blocks import list_blocked
from app.services.presence import online_map
from app.services.users import delete_user_account, save_avatar, search_users

router = APIRouter(prefix="/users", tags=["users"])


@router.get("/search", response_model=list[UserSearchResult])
async def search(
    current_user: CurrentUser,
    db: DbSession,
    q: str = Query(min_length=1, max_length=80),
) -> list[UserSearchResult]:
    users = await search_users(db, q, current_user.id)
    redis = await get_redis()
    online = await online_map(redis, [user.id for user in users])
    return [
        UserSearchResult(
            id=user.id,
            username=user.username,
            display_name=user.display_name,
            avatar_url=user.avatar_url,
            last_seen_at=user.last_seen_at,
            is_online=online.get(user.id, False),
        )
        for user in users
    ]


@router.get("/me/profile", response_model=UserPublic)
async def get_profile(current_user: CurrentUser) -> UserPublic:
    return UserPublic.model_validate(current_user)


@router.patch("/me/profile", response_model=UserPublic)
async def update_profile(payload: ProfileUpdate, current_user: CurrentUser, db: DbSession) -> UserPublic:
    if payload.display_name is not None:
        current_user.display_name = payload.display_name
    if payload.email is not None:
        email = str(payload.email).lower()
        existing = (
            await db.scalars(select(User).where(User.email == email, User.id != current_user.id))
        ).first()
        if existing is not None:
            raise HTTPException(status.HTTP_409_CONFLICT, "Email already exists")
        current_user.email = email
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "Email already exists") from exc
    await db.refresh(current_user)
    return UserPublic.model_validate(current_user)


@router.post("/me/avatar", response_model=UserPublic)
async def upload_avatar(
    current_user: CurrentUser,
    db: DbSession,
    file: Annotated[UploadFile, File(...)],
) -> UserPublic:
    user = await save_avatar(db, current_user, file)
    return UserPublic.model_validate(user)


@router.get("/avatar/{filename}")
async def get_avatar(filename: str, exp: int, sig: str) -> FileResponse:
    if Path(filename).name != filename or "/" in filename or ".." in filename:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "File missing from storage")
    url = f"/uploads/avatars/{filename}"
    if not verify_avatar_url(url, exp, sig):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Invalid avatar link")
    path = get_settings().upload_dir / "avatars" / filename
    if not path.is_file():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "File missing from storage")
    media_type, _ = mimetypes.guess_type(filename)
    remaining = max(0, exp - int(time.time()))
    max_age = min(remaining, 7 * 24 * 3600)
    return FileResponse(
        path,
        media_type=media_type or "application/octet-stream",
        headers={"Cache-Control": f"private, max-age={max_age}"},
    )


@router.post("/{user_id}/block", status_code=status.HTTP_204_NO_CONTENT)
async def block_user(user_id: str, current_user: CurrentUser, db: DbSession) -> Response:
    if user_id == current_user.id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Cannot block yourself")
    target = await db.get(User, user_id)
    if target is None or getattr(target, "deleted_at", None) is not None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")
    existing = (
        await db.scalars(
            select(UserBlock.id).where(
                UserBlock.blocker_id == current_user.id,
                UserBlock.blocked_id == user_id,
            )
        )
    ).first()
    if existing is None:
        db.add(UserBlock(blocker_id=current_user.id, blocked_id=user_id))
        try:
            await db.commit()
        except IntegrityError:
            await db.rollback()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete("/{user_id}/block", status_code=status.HTTP_204_NO_CONTENT)
async def unblock_user(user_id: str, current_user: CurrentUser, db: DbSession) -> Response:
    row = (
        await db.scalars(
            select(UserBlock).where(
                UserBlock.blocker_id == current_user.id,
                UserBlock.blocked_id == user_id,
            )
        )
    ).first()
    if row is not None:
        await db.delete(row)
        await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/me/blocked", response_model=list[UserSearchResult])
async def get_blocked(current_user: CurrentUser, db: DbSession) -> list[UserSearchResult]:
    blocked = await list_blocked(db, current_user.id)
    redis = await get_redis()
    online = await online_map(redis, [user.id for user in blocked])
    return [
        UserSearchResult(
            id=user.id,
            username=user.username,
            display_name=user.display_name,
            avatar_url=user.avatar_url,
            last_seen_at=user.last_seen_at,
            is_online=online.get(user.id, False),
        )
        for user in blocked
    ]


@router.delete("/me", status_code=status.HTTP_204_NO_CONTENT)
async def delete_account(
    payload: AccountDeleteRequest, current_user: CurrentUser, db: DbSession
) -> Response:
    await delete_user_account(db, current_user)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
