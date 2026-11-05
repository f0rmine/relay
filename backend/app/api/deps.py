from typing import Annotated, Any

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.redis import get_redis
from app.core.security import decode_jwt_token
from app.models.user import User

security = HTTPBearer(auto_error=False)
DbSession = Annotated[AsyncSession, Depends(get_db)]


async def ensure_access_token_usable(payload: dict[str, Any]) -> None:
    redis = await get_redis()
    if await redis.exists(f"revoked:jti:{payload['jti']}"):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid token")
    min_iat = await redis.get(f"auth:min_iat:{payload['sub']}")
    if min_iat is not None and int(payload["iat"]) < int(min_iat):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Token expired")


async def get_current_user(
    db: DbSession,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(security)],
) -> User:
    if credentials is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Missing bearer token")
    payload = decode_jwt_token(credentials.credentials, "access")
    await ensure_access_token_usable(payload)
    user = await db.get(User, payload["sub"])
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "User not found")
    if getattr(user, "deleted_at", None) is not None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "User not found")
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


async def get_access_token_payload(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(security)],
) -> dict[str, Any]:
    if credentials is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Missing bearer token")
    return decode_jwt_token(credentials.credentials, "access")


AccessTokenPayload = Annotated[dict[str, Any], Depends(get_access_token_payload)]


async def get_ws_user_from_token(db: AsyncSession, token: str | None) -> User:
    if not token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Missing token")
    payload = decode_jwt_token(token, "access")
    await ensure_access_token_usable(payload)
    user = await db.get(User, payload["sub"])
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "User not found")
    if getattr(user, "deleted_at", None) is not None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "User not found")
    return user
