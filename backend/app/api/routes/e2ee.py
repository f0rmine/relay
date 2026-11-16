from fastapi import APIRouter, HTTPException, Path, status

from app.api.deps import CurrentUser, DbSession
from app.core.rate_limit import hit_rate_limit
from app.schemas.e2ee import (
    ClaimedBundleOut,
    DeviceRegister,
    IdentityOut,
    IdentityPut,
    OwnDeviceOut,
    PrekeyCounts,
    PrekeyUpload,
    UserKeysOut,
)
from app.services import e2ee as service

router = APIRouter(prefix="/e2ee", tags=["e2ee"])

DeviceId = Path(min_length=8, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")

WRITE_LIMIT_PER_HOUR = 30
# One claim consumes one-time prekeys, so cap it to stop a user draining someone
# else's supply (they would fall back to the signed / last-resort keys).
CLAIM_LIMIT_PER_HOUR = 120


async def _limit(key: str, limit: int) -> None:
    if not await hit_rate_limit(key, limit, 3600):
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Too many requests")


@router.put("/identity", response_model=IdentityOut)
async def put_identity(payload: IdentityPut, current_user: CurrentUser, db: DbSession) -> IdentityOut:
    await _limit(f"rate_limit:e2ee:write:{current_user.id}", WRITE_LIMIT_PER_HOUR)
    return await service.put_identity(db, current_user, payload)


@router.post("/devices", response_model=OwnDeviceOut)
async def register_device(
    payload: DeviceRegister, current_user: CurrentUser, db: DbSession
) -> OwnDeviceOut:
    await _limit(f"rate_limit:e2ee:write:{current_user.id}", WRITE_LIMIT_PER_HOUR)
    return await service.register_device(db, current_user, payload)


@router.get("/devices", response_model=list[OwnDeviceOut])
async def list_own_devices(current_user: CurrentUser, db: DbSession) -> list[OwnDeviceOut]:
    return await service.list_own_devices(db, current_user)


@router.put("/devices/{device_id}/prekeys", response_model=PrekeyCounts)
async def upload_prekeys(
    payload: PrekeyUpload,
    current_user: CurrentUser,
    db: DbSession,
    device_id: str = DeviceId,
) -> PrekeyCounts:
    await _limit(f"rate_limit:e2ee:write:{current_user.id}", WRITE_LIMIT_PER_HOUR)
    return await service.upload_prekeys(db, current_user, device_id, payload)


@router.delete("/devices/{device_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_device(current_user: CurrentUser, db: DbSession, device_id: str = DeviceId) -> None:
    await service.revoke_device(db, current_user, device_id)


@router.get("/users/{user_id}", response_model=UserKeysOut)
async def get_user_keys(user_id: str, current_user: CurrentUser, db: DbSession) -> UserKeysOut:
    return await service.get_user_keys(db, current_user, user_id)


@router.post("/users/{user_id}/devices/{device_id}/claim", response_model=ClaimedBundleOut)
async def claim_bundle(
    user_id: str,
    current_user: CurrentUser,
    db: DbSession,
    device_id: str = DeviceId,
) -> ClaimedBundleOut:
    await _limit(f"rate_limit:e2ee:claim:{current_user.id}", CLAIM_LIMIT_PER_HOUR)
    return await service.claim_bundle(db, current_user, user_id, device_id)
