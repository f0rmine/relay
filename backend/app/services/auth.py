from datetime import UTC, datetime, timedelta
from uuid import uuid4

from fastapi import HTTPException, status
from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
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
        avatar_url=None,
        password_hash=hash_password(password),
    )
    db.add(user)
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        existing = (
            await db.scalars(select(User).where(or_(User.username == username, User.email == email)))
        ).first()
        detail = (
            "Username already exists"
            if existing is not None and existing.username == username
            else "Email already exists"
        )
        raise HTTPException(status.HTTP_409_CONFLICT, detail) from exc
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


def _add_token_pair(db: AsyncSession, user: User) -> tuple[str, str]:
    settings = get_settings()
    access = create_jwt_token(
        user.id, "access", timedelta(minutes=settings.access_token_expire_minutes)
    )
    refresh_jti = str(uuid4())
    refresh = create_jwt_token(
        user.id,
        "refresh",
        timedelta(days=settings.refresh_token_expire_days),
        extra={"jti": refresh_jti},
    )
    token_row = RefreshToken(
        user_id=user.id,
        jti=refresh_jti,
        token_hash=hash_token(refresh),
        expires_at=datetime.now(UTC) + timedelta(days=settings.refresh_token_expire_days),
    )
    db.add(token_row)
    return access, refresh


async def issue_tokens(db: AsyncSession, user: User) -> tuple[str, str]:
    access, refresh = _add_token_pair(db, user)
    await db.commit()
    return access, refresh


async def refresh_access_token(db: AsyncSession, refresh_token: str) -> tuple[User, str, str]:
    from app.core.security import decode_jwt_token

    payload = decode_jwt_token(refresh_token, "refresh")
    user = await db.get(User, payload["sub"])
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid refresh token")
    now = datetime.now(UTC)
    base_query = select(RefreshToken).where(
        RefreshToken.user_id == user.id,
        RefreshToken.revoked_at.is_(None),
        RefreshToken.expires_at > now,
    )
    token_row = (
        await db.scalars(base_query.where(RefreshToken.jti == payload["jti"]).with_for_update())
    ).first()
    if token_row is None:
        legacy_rows = (
            await db.scalars(base_query.where(RefreshToken.jti.is_(None)).with_for_update())
        ).all()
        token_row = next(
            (row for row in legacy_rows if verify_token_hash(refresh_token, row.token_hash)), None
        )
    elif not verify_token_hash(refresh_token, token_row.token_hash):
        token_row = None
    if token_row is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid refresh token")
    token_row.revoked_at = now
    access, new_refresh = _add_token_pair(db, user)
    await db.commit()
    return user, access, new_refresh


async def revoke_refresh_token(db: AsyncSession, user_id: str, refresh_token: str | None) -> None:
    from app.core.security import decode_jwt_token

    now = datetime.now(UTC)
    query = select(RefreshToken).where(
        RefreshToken.user_id == user_id,
        RefreshToken.revoked_at.is_(None),
        RefreshToken.expires_at > now,
    )
    if refresh_token is not None:
        try:
            payload = decode_jwt_token(refresh_token, "refresh")
        except HTTPException:
            return
        modern_row = (
            await db.scalars(query.where(RefreshToken.jti == payload["jti"]).with_for_update())
        ).first()
        rows = [modern_row] if modern_row is not None else list(
            (
                await db.scalars(query.where(RefreshToken.jti.is_(None)).with_for_update())
            ).all()
        )
    else:
        rows = list((await db.scalars(query.with_for_update())).all())
    for row in rows:
        if refresh_token is None or verify_token_hash(refresh_token, row.token_hash):
            row.revoked_at = now
    await db.commit()


async def create_password_reset_token(db: AsyncSession, email: str) -> str | None:
    user = (await db.scalars(select(User).where(User.email == email.lower()))).first()
    if user is None:
        return None
    token_jti = str(uuid4())
    token = create_jwt_token(
        user.id, "password_reset", timedelta(hours=1), extra={"jti": token_jti}
    )
    db.add(
        PasswordResetToken(
            user_id=user.id,
            jti=token_jti,
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
    query = select(PasswordResetToken).where(
        PasswordResetToken.user_id == user.id,
        PasswordResetToken.used_at.is_(None),
        PasswordResetToken.expires_at > datetime.now(UTC),
    )
    token_row = (
        await db.scalars(
            query.where(PasswordResetToken.jti == payload["jti"]).with_for_update()
        )
    ).first()
    if token_row is None:
        legacy_rows = (
            await db.scalars(query.where(PasswordResetToken.jti.is_(None)).with_for_update())
        ).all()
        token_row = next((row for row in legacy_rows if verify_token_hash(token, row.token_hash)), None)
    elif not verify_token_hash(token, token_row.token_hash):
        token_row = None
    if token_row is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid reset token")
    user.password_hash = hash_password(new_password)
    now = datetime.now(UTC)
    rows = (
        await db.scalars(
            select(PasswordResetToken)
            .where(
                PasswordResetToken.user_id == user.id,
                PasswordResetToken.used_at.is_(None),
                PasswordResetToken.expires_at > now,
            )
            .with_for_update()
        )
    ).all()
    for row in rows:
        row.used_at = now
    refresh_tokens = (
        await db.scalars(
            select(RefreshToken)
            .where(
                RefreshToken.user_id == user.id,
                RefreshToken.revoked_at.is_(None),
            )
            .with_for_update()
        )
    ).all()
    for refresh_token in refresh_tokens:
        refresh_token.revoked_at = now
    await db.commit()
