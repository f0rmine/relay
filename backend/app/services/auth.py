from datetime import UTC, datetime, timedelta

from fastapi import HTTPException, status
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.security import (
    create_jwt_token,
    hash_password,
    hash_token,
    verify_password,
    verify_token_hash,
)
from app.models.auth import PasswordResetToken, RefreshToken
from app.models.user import User
from app.services.users import placeholder_avatar


async def register_user(
    db: AsyncSession, username: str, display_name: str, email: str, password: str
) -> User:
    username = username.lower()
    email = email.lower()
    existing = (
        await db.scalars(select(User).where(or_(User.username == username, User.email == email)))
    ).first()
    if existing:
        detail = "Username already exists" if existing.username == username else "Email already exists"
        raise HTTPException(status.HTTP_409_CONFLICT, detail)

    user = User(
        username=username,
        display_name=display_name,
        email=email,
        avatar_url=placeholder_avatar(username),
        password_hash=hash_password(password),
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


async def authenticate_user(db: AsyncSession, login: str, password: str) -> User:
    login = login.lower()
    user = (
        await db.scalars(select(User).where(or_(User.username == login, User.email == login)))
    ).first()
    if user is None or not verify_password(password, user.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid credentials")
    return user


async def issue_tokens(db: AsyncSession, user: User) -> tuple[str, str]:
    settings = get_settings()
    access = create_jwt_token(
        user.id, "access", timedelta(minutes=settings.access_token_expire_minutes)
    )
    refresh = create_jwt_token(
        user.id, "refresh", timedelta(days=settings.refresh_token_expire_days)
    )
    token_row = RefreshToken(
        user_id=user.id,
        token_hash=hash_token(refresh),
        expires_at=datetime.now(UTC) + timedelta(days=settings.refresh_token_expire_days),
    )
    db.add(token_row)
    await db.commit()
    return access, refresh


async def refresh_access_token(db: AsyncSession, refresh_token: str) -> tuple[User, str, str]:
    from app.core.security import decode_jwt_token

    payload = decode_jwt_token(refresh_token, "refresh")
    user = await db.get(User, payload["sub"])
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid refresh token")
    now = datetime.now(UTC)
    rows = (
        await db.scalars(
            select(RefreshToken).where(
                RefreshToken.user_id == user.id,
                RefreshToken.revoked_at.is_(None),
                RefreshToken.expires_at > now,
            )
        )
    ).all()
    token_row = next((row for row in rows if verify_token_hash(refresh_token, row.token_hash)), None)
    if token_row is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid refresh token")
    token_row.revoked_at = now
    access, new_refresh = await issue_tokens(db, user)
    await db.commit()
    return user, access, new_refresh


async def revoke_refresh_token(db: AsyncSession, user_id: str, refresh_token: str | None) -> None:
    now = datetime.now(UTC)
    rows = (
        await db.scalars(
            select(RefreshToken).where(
                RefreshToken.user_id == user_id,
                RefreshToken.revoked_at.is_(None),
                RefreshToken.expires_at > now,
            )
        )
    ).all()
    for row in rows:
        if refresh_token is None or verify_token_hash(refresh_token, row.token_hash):
            row.revoked_at = now
    await db.commit()


async def create_password_reset_token(db: AsyncSession, email: str) -> str | None:
    user = (await db.scalars(select(User).where(User.email == email.lower()))).first()
    if user is None:
        return None
    token = create_jwt_token(user.id, "password_reset", timedelta(hours=1))
    db.add(
        PasswordResetToken(
            user_id=user.id,
            token_hash=hash_token(token),
            expires_at=datetime.now(UTC) + timedelta(hours=1),
        )
    )
    await db.commit()
    return token


async def reset_password(db: AsyncSession, token: str, new_password: str) -> None:
    from app.core.security import decode_jwt_token

    payload = decode_jwt_token(token, "password_reset")
    user = await db.get(User, payload["sub"])
    if user is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid reset token")
    rows = (
        await db.scalars(
            select(PasswordResetToken).where(
                PasswordResetToken.user_id == user.id,
                PasswordResetToken.used_at.is_(None),
                PasswordResetToken.expires_at > datetime.now(UTC),
            )
        )
    ).all()
    token_row = next((row for row in rows if verify_token_hash(token, row.token_hash)), None)
    if token_row is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid reset token")
    user.password_hash = hash_password(new_password)
    now = datetime.now(UTC)
    for row in rows:
        row.used_at = now
    refresh_tokens = (
        await db.scalars(
            select(RefreshToken).where(
                RefreshToken.user_id == user.id,
                RefreshToken.revoked_at.is_(None),
            )
        )
    ).all()
    for refresh_token in refresh_tokens:
        refresh_token.revoked_at = now
    await db.commit()
