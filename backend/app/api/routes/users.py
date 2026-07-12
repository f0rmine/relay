from fastapi import APIRouter, File, HTTPException, Query, UploadFile, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.api.deps import CurrentUser, DbSession
from app.core.redis import get_redis
from app.models.user import User
from app.schemas.user import ProfileUpdate, UserPublic, UserSearchResult
from app.services.presence import online_map
from app.services.users import save_avatar, search_users

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
    current_user: CurrentUser, db: DbSession, file: UploadFile = File(...)
) -> UserPublic:
    user = await save_avatar(db, current_user, file)
    return UserPublic.model_validate(user)
