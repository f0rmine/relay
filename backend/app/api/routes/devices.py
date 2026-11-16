from datetime import UTC, datetime

from fastapi import APIRouter, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.api.deps import CurrentUser, DbSession
from app.models.device import DeviceToken
from app.schemas.device import DeviceTokenRegister, DeviceTokenRemove

router = APIRouter(prefix="/devices", tags=["devices"])


def update_device_token(token: DeviceToken, payload: DeviceTokenRegister, user_id: str) -> None:
    token.user_id = user_id
    token.platform = payload.platform
    token.locale = payload.locale
    token.device_id = payload.device_id
    token.enabled = True
    token.last_seen_at = datetime.now(UTC)


@router.post("/push-token", status_code=status.HTTP_204_NO_CONTENT)
async def register_push_token(
    payload: DeviceTokenRegister, current_user: CurrentUser, db: DbSession
) -> None:
    existing = (
        await db.scalars(select(DeviceToken).where(DeviceToken.token == payload.token))
    ).first()
    if existing:
        update_device_token(existing, payload, current_user.id)
    else:
        db.add(
            DeviceToken(
                user_id=current_user.id,
                token=payload.token,
                platform=payload.platform,
                locale=payload.locale,
                device_id=payload.device_id,
                enabled=True,
                last_seen_at=datetime.now(UTC),
            )
        )
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        existing = (
            await db.scalars(select(DeviceToken).where(DeviceToken.token == payload.token))
        ).first()
        if existing is None:
            raise
        update_device_token(existing, payload, current_user.id)
        await db.commit()


@router.delete("/push-token", status_code=status.HTTP_204_NO_CONTENT)
async def remove_push_token(
    payload: DeviceTokenRemove, current_user: CurrentUser, db: DbSession
) -> None:
    existing = (
        await db.scalars(
            select(DeviceToken).where(
                DeviceToken.token == payload.token,
                DeviceToken.user_id == current_user.id,
            )
        )
    ).first()
    if existing:
        existing.enabled = False
        await db.commit()
