"""E2EE key directory: identities, devices and prekeys (Phase 1)."""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import HTTPException, status
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import e2ee_wire as wire
from app.core.security import verify_password
from app.models.e2ee import E2eeDevice, E2eeIdentity, E2eeOneTimePrekey
from app.models.user import User
from app.schemas.e2ee import (
    ClaimedBundleOut,
    DeviceOut,
    DeviceRegister,
    IdentityOut,
    IdentityPut,
    OneTimePrekeyIn,
    OneTimePrekeyOut,
    OwnDeviceOut,
    PqPrekeyIn,
    PqPrekeyOut,
    PrekeyCounts,
    PrekeyUpload,
    SignedPrekeyIn,
    SignedPrekeyOut,
    UserKeysOut,
)
from app.services.blocks import is_blocked

MAX_ACTIVE_DEVICES = 10
MAX_STORED_EC_PREKEYS = 200
MAX_STORED_KEM_PREKEYS = 100

EC = "ec"
KEM = "kem"


def _bad_request(exc: wire.WireError) -> HTTPException:
    return HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))


# ---------------------------------------------------------------- identity


async def _identity(db: AsyncSession, user_id: str) -> E2eeIdentity | None:
    return await db.scalar(select(E2eeIdentity).where(E2eeIdentity.user_id == user_id))


async def _revoke_devices(db: AsyncSession, user_id: str, now: datetime) -> int:
    devices = (
        await db.scalars(
            select(E2eeDevice).where(
                E2eeDevice.user_id == user_id, E2eeDevice.revoked_at.is_(None)
            )
        )
    ).all()
    for device in devices:
        device.revoked_at = now
        await db.execute(delete(E2eeOneTimePrekey).where(E2eeOneTimePrekey.device_pk == device.id))
    return len(devices)


async def put_identity(db: AsyncSession, user: User, payload: IdentityPut) -> IdentityOut:
    try:
        wire.b64decode(payload.identity_key, wire.ED25519_KEY_BYTES, "identity_key")
    except wire.WireError as exc:
        raise _bad_request(exc) from exc

    existing = await _identity(db, user.id)
    if existing is None:
        db.add(E2eeIdentity(user_id=user.id, identity_key=payload.identity_key))
        await db.commit()
        return IdentityOut(identity_key=payload.identity_key)
    if existing.identity_key == payload.identity_key:
        return IdentityOut(identity_key=existing.identity_key)
    if not payload.replace:
        raise HTTPException(status.HTTP_409_CONFLICT, "An identity key is already registered")
    if not payload.password or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Password is required to replace the identity key")

    # Every device was signed by the old identity, so none of them stay valid.
    revoked = await _revoke_devices(db, user.id, datetime.now(UTC))
    existing.identity_key = payload.identity_key
    await db.commit()
    return IdentityOut(identity_key=payload.identity_key, revoked_devices=revoked)


# ------------------------------------------------------------------ prekeys


def _verify_signed_prekey(device_id: str, signing_key: bytes, prekey: SignedPrekeyIn) -> None:
    public = wire.b64decode(prekey.public_key, wire.X25519_KEY_BYTES, "signed_prekey")
    signature = wire.b64decode(prekey.signature, wire.ED25519_SIG_BYTES, "signed_prekey signature")
    message = wire.prekey_message(wire.SIGNED_PREKEY_LABEL, device_id, prekey.key_id, public)
    wire.verify(signing_key, signature, message, "signed_prekey")


def _verify_pq_prekey(device_id: str, signing_key: bytes, prekey: PqPrekeyIn) -> None:
    public = wire.b64decode(prekey.public_key, wire.MLKEM768_PUBLIC_KEY_BYTES, "pq_prekey")
    signature = wire.b64decode(prekey.signature, wire.ED25519_SIG_BYTES, "pq_prekey signature")
    message = wire.prekey_message(wire.PQ_PREKEY_LABEL, device_id, prekey.key_id, public)
    wire.verify(signing_key, signature, message, "pq_prekey")


def _verify_one_time_prekeys(
    device_id: str,
    signing_key: bytes,
    ec_keys: list[OneTimePrekeyIn],
    kem_keys: list[PqPrekeyIn],
) -> None:
    for key in ec_keys:
        wire.b64decode(key.public_key, wire.X25519_KEY_BYTES, "one_time_prekey")
    for kem_key in kem_keys:
        _verify_pq_prekey(device_id, signing_key, kem_key)
    for kind, ids in ((EC, [k.key_id for k in ec_keys]), (KEM, [k.key_id for k in kem_keys])):
        if len(ids) != len(set(ids)):
            raise wire.WireError(f"duplicate {kind} one-time prekey ids")


async def _prekey_counts(db: AsyncSession, device_pk: str) -> PrekeyCounts:
    rows = (
        await db.execute(
            select(E2eeOneTimePrekey.kind, func.count())
            .where(E2eeOneTimePrekey.device_pk == device_pk)
            .group_by(E2eeOneTimePrekey.kind)
        )
    ).all()
    counts = {kind: count for kind, count in rows}
    return PrekeyCounts(
        one_time_prekeys=counts.get(EC, 0), pq_one_time_prekeys=counts.get(KEM, 0)
    )


async def _store_one_time_prekeys(
    db: AsyncSession,
    device: E2eeDevice,
    ec_keys: list[OneTimePrekeyIn],
    kem_keys: list[PqPrekeyIn],
) -> None:
    existing = {
        (row.kind, row.key_id): row.public_key
        for row in (
            await db.scalars(
                select(E2eeOneTimePrekey).where(E2eeOneTimePrekey.device_pk == device.id)
            )
        ).all()
    }
    fresh: list[E2eeOneTimePrekey] = []
    incoming: list[tuple[str, int, str, str | None]] = [
        (EC, k.key_id, k.public_key, None) for k in ec_keys
    ] + [(KEM, k.key_id, k.public_key, k.signature) for k in kem_keys]
    for kind, key_id, public_key, signature in incoming:
        stored = existing.get((kind, key_id))
        if stored is not None:
            # Identical re-upload (a retried request) is fine; a different key is a client bug.
            if stored != public_key:
                raise HTTPException(status.HTTP_409_CONFLICT, f"{kind} prekey id {key_id} already used")
            continue
        fresh.append(
            E2eeOneTimePrekey(
                device_pk=device.id,
                kind=kind,
                key_id=key_id,
                public_key=public_key,
                signature=signature,
            )
        )

    ec_total = sum(1 for kind, _ in existing if kind == EC) + sum(1 for p in fresh if p.kind == EC)
    kem_total = sum(1 for kind, _ in existing if kind == KEM) + sum(1 for p in fresh if p.kind == KEM)
    if ec_total > MAX_STORED_EC_PREKEYS or kem_total > MAX_STORED_KEM_PREKEYS:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Too many stored one-time prekeys")
    db.add_all(fresh)


# ------------------------------------------------------------------ devices


def _device_out(device: E2eeDevice, *, include_label: bool) -> DeviceOut:
    return DeviceOut(
        device_id=device.device_id,
        signing_key=device.signing_key,
        agreement_key=device.agreement_key,
        identity_signature=device.identity_signature,
        signed_prekey=SignedPrekeyOut(
            key_id=device.signed_prekey_id,
            public_key=device.signed_prekey,
            signature=device.signed_prekey_signature,
        ),
        pq_prekey=PqPrekeyOut(
            key_id=device.pq_prekey_id,
            public_key=device.pq_prekey,
            signature=device.pq_prekey_signature,
        ),
        created_at=device.created_at,
        label=device.label if include_label else None,
    )


async def _own_device(db: AsyncSession, user: User, device_id: str) -> E2eeDevice:
    device = await db.scalar(
        select(E2eeDevice).where(
            E2eeDevice.user_id == user.id,
            E2eeDevice.device_id == device_id,
            E2eeDevice.revoked_at.is_(None),
        )
    )
    if device is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Device not found")
    return device


def _apply_prekeys(
    device: E2eeDevice, signed: SignedPrekeyIn | None, pq: PqPrekeyIn | None
) -> None:
    if signed is not None:
        device.signed_prekey_id = signed.key_id
        device.signed_prekey = signed.public_key
        device.signed_prekey_signature = signed.signature
    if pq is not None:
        device.pq_prekey_id = pq.key_id
        device.pq_prekey = pq.public_key
        device.pq_prekey_signature = pq.signature


async def register_device(db: AsyncSession, user: User, payload: DeviceRegister) -> OwnDeviceOut:
    identity = await _identity(db, user.id)
    if identity is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Register an identity key first")

    try:
        identity_key = wire.b64decode(identity.identity_key, wire.ED25519_KEY_BYTES, "identity_key")
        signing_key = wire.b64decode(payload.signing_key, wire.ED25519_KEY_BYTES, "signing_key")
        agreement_key = wire.b64decode(payload.agreement_key, wire.X25519_KEY_BYTES, "agreement_key")
        signature = wire.b64decode(
            payload.identity_signature, wire.ED25519_SIG_BYTES, "identity_signature"
        )
        wire.verify(
            identity_key,
            signature,
            wire.device_message(user.id, payload.device_id, signing_key, agreement_key),
            "identity_signature",
        )
        _verify_signed_prekey(payload.device_id, signing_key, payload.signed_prekey)
        _verify_pq_prekey(payload.device_id, signing_key, payload.pq_prekey)
        _verify_one_time_prekeys(
            payload.device_id, signing_key, payload.one_time_prekeys, payload.pq_one_time_prekeys
        )
    except wire.WireError as exc:
        raise _bad_request(exc) from exc

    now = datetime.now(UTC)
    device = await db.scalar(
        select(E2eeDevice).where(
            E2eeDevice.user_id == user.id, E2eeDevice.device_id == payload.device_id
        )
    )
    if device is not None:
        if device.revoked_at is not None:
            raise HTTPException(status.HTTP_409_CONFLICT, "This device id was revoked")
        if (device.signing_key, device.agreement_key) != (payload.signing_key, payload.agreement_key):
            raise HTTPException(status.HTTP_409_CONFLICT, "Device id already registered with other keys")
        device.identity_signature = payload.identity_signature
    else:
        active = await db.scalar(
            select(func.count())
            .select_from(E2eeDevice)
            .where(E2eeDevice.user_id == user.id, E2eeDevice.revoked_at.is_(None))
        )
        if (active or 0) >= MAX_ACTIVE_DEVICES:
            raise HTTPException(status.HTTP_409_CONFLICT, "Too many active devices")
        device = E2eeDevice(
            user_id=user.id,
            device_id=payload.device_id,
            signing_key=payload.signing_key,
            agreement_key=payload.agreement_key,
            identity_signature=payload.identity_signature,
            signed_prekey_id=payload.signed_prekey.key_id,
            signed_prekey=payload.signed_prekey.public_key,
            signed_prekey_signature=payload.signed_prekey.signature,
            pq_prekey_id=payload.pq_prekey.key_id,
            pq_prekey=payload.pq_prekey.public_key,
            pq_prekey_signature=payload.pq_prekey.signature,
        )
        db.add(device)
        await db.flush()

    device.label = payload.label
    device.last_seen_at = now
    _apply_prekeys(device, payload.signed_prekey, payload.pq_prekey)
    await _store_one_time_prekeys(db, device, payload.one_time_prekeys, payload.pq_one_time_prekeys)
    await db.commit()
    await db.refresh(device)
    return await own_device_out(db, device)


async def own_device_out(db: AsyncSession, device: E2eeDevice) -> OwnDeviceOut:
    base = _device_out(device, include_label=True)
    return OwnDeviceOut(
        **base.model_dump(),
        last_seen_at=device.last_seen_at,
        prekeys=await _prekey_counts(db, device.id),
    )


async def upload_prekeys(
    db: AsyncSession, user: User, device_id: str, payload: PrekeyUpload
) -> PrekeyCounts:
    device = await _own_device(db, user, device_id)
    try:
        signing_key = wire.b64decode(device.signing_key, wire.ED25519_KEY_BYTES, "signing_key")
        if payload.signed_prekey is not None:
            _verify_signed_prekey(device_id, signing_key, payload.signed_prekey)
        if payload.pq_prekey is not None:
            _verify_pq_prekey(device_id, signing_key, payload.pq_prekey)
        _verify_one_time_prekeys(
            device_id, signing_key, payload.one_time_prekeys, payload.pq_one_time_prekeys
        )
    except wire.WireError as exc:
        raise _bad_request(exc) from exc

    _apply_prekeys(device, payload.signed_prekey, payload.pq_prekey)
    await _store_one_time_prekeys(db, device, payload.one_time_prekeys, payload.pq_one_time_prekeys)
    device.last_seen_at = datetime.now(UTC)
    await db.commit()
    return await _prekey_counts(db, device.id)


async def list_own_devices(db: AsyncSession, user: User) -> list[OwnDeviceOut]:
    devices = (
        await db.scalars(
            select(E2eeDevice)
            .where(E2eeDevice.user_id == user.id, E2eeDevice.revoked_at.is_(None))
            .order_by(E2eeDevice.created_at)
        )
    ).all()
    return [await own_device_out(db, device) for device in devices]


async def revoke_device(db: AsyncSession, user: User, device_id: str) -> None:
    device = await _own_device(db, user, device_id)
    device.revoked_at = datetime.now(UTC)
    await db.execute(delete(E2eeOneTimePrekey).where(E2eeOneTimePrekey.device_pk == device.id))
    await db.commit()


# ---------------------------------------------------------- other users' keys


async def _visible_identity(db: AsyncSession, requester: User, user_id: str) -> E2eeIdentity:
    """Return a user's identity, hiding deleted accounts and blocks in either direction."""
    target = await db.scalar(select(User).where(User.id == user_id))
    identity = await _identity(db, user_id)
    if (
        target is None
        or target.deleted_at is not None
        or identity is None
        or (requester.id != user_id and await is_blocked(db, requester.id, user_id))
    ):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Keys not found")
    return identity


async def get_user_keys(db: AsyncSession, requester: User, user_id: str) -> UserKeysOut:
    identity = await _visible_identity(db, requester, user_id)
    devices = (
        await db.scalars(
            select(E2eeDevice)
            .where(E2eeDevice.user_id == user_id, E2eeDevice.revoked_at.is_(None))
            .order_by(E2eeDevice.created_at)
        )
    ).all()
    own = requester.id == user_id
    return UserKeysOut(
        user_id=user_id,
        identity_key=identity.identity_key,
        devices=[_device_out(device, include_label=own) for device in devices],
    )


async def _claim_one(db: AsyncSession, device_pk: str, kind: str) -> E2eeOneTimePrekey | None:
    prekey = await db.scalar(
        select(E2eeOneTimePrekey)
        .where(E2eeOneTimePrekey.device_pk == device_pk, E2eeOneTimePrekey.kind == kind)
        .order_by(E2eeOneTimePrekey.key_id)
        .limit(1)
        # Postgres: concurrent claimers skip each other's rows instead of
        # double-issuing one key. SQLite serialises writes anyway.
        .with_for_update(skip_locked=True)
    )
    if prekey is not None:
        await db.delete(prekey)
    return prekey


async def claim_bundle(
    db: AsyncSession, requester: User, user_id: str, device_id: str
) -> ClaimedBundleOut:
    identity = await _visible_identity(db, requester, user_id)
    device = await db.scalar(
        select(E2eeDevice).where(
            E2eeDevice.user_id == user_id,
            E2eeDevice.device_id == device_id,
            E2eeDevice.revoked_at.is_(None),
        )
    )
    if device is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Device not found")

    ec = await _claim_one(db, device.id, EC)
    kem = await _claim_one(db, device.id, KEM)
    out = ClaimedBundleOut(
        user_id=user_id,
        identity_key=identity.identity_key,
        device=_device_out(device, include_label=requester.id == user_id),
        one_time_prekey=OneTimePrekeyOut(key_id=ec.key_id, public_key=ec.public_key) if ec else None,
        pq_one_time_prekey=(
            PqPrekeyOut(key_id=kem.key_id, public_key=kem.public_key, signature=kem.signature or "")
            if kem
            else None
        ),
    )
    await db.commit()
    return out
