from datetime import UTC, datetime

from fastapi import APIRouter, status
from sqlalchemy import select

from app.api.deps import CurrentUser, DbSession
from app.models.device import DeviceToken
from app.schemas.device import DeviceTokenRegister, DeviceTokenRemove

router = APIRouter(prefix="/devices", tags=["devices"])


@router.post("/push-token", status_code=status.HTTP_204_NO_CONTENT)
async def register_push_token(
    payload: DeviceTokenRegister, current_user: CurrentUser, db: DbSession
) -> None:
    existing = (
        await db.scalars(select(DeviceToken).where(DeviceToken.token == payload.token))
    ).first()
    now = datetime.now(UTC)
    if existing:
        existing.user_id = current_user.id
        existing.platform = payload.platform
        existing.device_id = payload.device_id
        existing.enabled = True
        existing.last_seen_at = now
    else:
        db.add(
            DeviceToken(
                user_id=current_user.id,
                token=payload.token,
                platform=payload.platform,
                device_id=payload.device_id,
                enabled=True,
                last_seen_at=now,
            )
        )
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
