import secrets
import string
from datetime import UTC, datetime, timedelta

import pyotp
from fastapi import HTTPException, status
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.encryption import AES_GCM_NONCE_BYTES, ENCRYPTION_VERSION, get_encryption_keyring
from app.core.rate_limit import hit_rate_limit
from app.core.security import create_jwt_token, decode_jwt_token, hash_password, verify_password
from app.models.recovery_code import RecoveryCode
from app.models.user import User

RECOVERY_CODE_COUNT = 10
RECOVERY_CODE_ALPHABET = string.ascii_uppercase + string.digits
CHALLENGE_TTL = timedelta(minutes=5)
VERIFY_RATE_LIMIT = 5
VERIFY_RATE_WINDOW_SECONDS = 300


def _totp_aad(user_id: str) -> bytes:
    return f"relay:totp:{user_id}:v1".encode()


def _pack_payload(ciphertext: bytes, nonce: bytes, key_id: str) -> bytes:
    key_id_bytes = key_id.encode()
    if len(key_id_bytes) > 255:
        raise ValueError("Encryption key id too long")
    return (
        bytes([ENCRYPTION_VERSION, len(key_id_bytes)])
        + key_id_bytes
        + nonce
        + ciphertext
    )


def _unpack_payload(data: bytes) -> tuple[bytes, bytes, str]:
    if len(data) < 2:
        raise ValueError("Invalid encrypted payload")
    version = data[0]
    if version != ENCRYPTION_VERSION:
        raise ValueError("Unsupported encryption version")
    key_id_len = data[1]
    key_id_end = 2 + key_id_len
    nonce_end = key_id_end + AES_GCM_NONCE_BYTES
    if len(data) <= nonce_end:
        raise ValueError("Invalid encrypted payload")
    key_id = data[2:key_id_end].decode()
    nonce = data[key_id_end:nonce_end]
    ciphertext = data[nonce_end:]
    return ciphertext, nonce, key_id


def _decrypt_totp_secret(user: User) -> str:
    if user.totp_secret_ciphertext is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "2FA setup not started")
    ciphertext, nonce, key_id = _unpack_payload(user.totp_secret_ciphertext)
    plaintext = get_encryption_keyring().decrypt(
        ciphertext,
        nonce,
        key_id,
        associated_data=_totp_aad(user.id),
    )
    return plaintext.decode("utf-8")


def _encrypt_totp_secret(user_id: str, secret: str) -> bytes:
    payload = get_encryption_keyring().encrypt(
        secret.encode("utf-8"), associated_data=_totp_aad(user_id)
    )
    return _pack_payload(payload.ciphertext, payload.nonce, payload.key_id)


def _verify_totp_code(secret: str, code: str) -> bool:
    cleaned = code.replace(" ", "").strip()
    if not cleaned.isdigit():
        return False
    try:
        return pyotp.TOTP(secret).verify(cleaned, valid_window=1)
    except Exception:  # noqa: BLE001
        return False


def _normalize_recovery_code(code: str) -> str:
    return code.replace("-", "").replace(" ", "").strip().upper()


def _display_recovery_code(canonical: str) -> str:
    return f"{canonical[:4]}-{canonical[4:]}"


def _generate_recovery_codes() -> list[str]:
    codes: list[str] = []
    seen: set[str] = set()
    while len(codes) < RECOVERY_CODE_COUNT:
        canonical = "".join(secrets.choice(RECOVERY_CODE_ALPHABET) for _ in range(8))
        if canonical in seen:
            continue
        seen.add(canonical)
        codes.append(canonical)
    return codes


async def _consume_recovery_code(db: AsyncSession, user: User, code: str) -> bool:
    if not code or not code.strip():
        return False
    normalized = _normalize_recovery_code(code)
    if len(normalized) != 8:
        return False
    rows = (
        await db.scalars(
            select(RecoveryCode).where(
                RecoveryCode.user_id == user.id, RecoveryCode.used_at.is_(None)
            )
        )
    ).all()
    for row in rows:
        if verify_password(normalized, row.code_hash):
            row.used_at = datetime.now(UTC)
            return True
    return False


async def setup_two_factor(db: AsyncSession, user: User) -> tuple[str, str]:
    if user.totp_enabled:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "2FA already enabled")
    if user.deleted_at is not None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid credentials")
    secret = pyotp.random_base32()
    user.totp_secret_ciphertext = _encrypt_totp_secret(user.id, secret)
    user.totp_enabled = False
    await db.commit()
    otpauth_url = pyotp.TOTP(secret).provisioning_uri(
        name=user.username, issuer_name="Relay"
    )
    return secret, otpauth_url


async def enable_two_factor(db: AsyncSession, user: User, code: str) -> list[str]:
    if user.totp_enabled:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "2FA already enabled")
    if user.totp_secret_ciphertext is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "2FA setup not started")
    secret = _decrypt_totp_secret(user)
    if not _verify_totp_code(secret, code):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid verification code")
    user.totp_enabled = True
    await db.execute(delete(RecoveryCode).where(RecoveryCode.user_id == user.id))
    canonical_codes = _generate_recovery_codes()
    for canonical in canonical_codes:
        db.add(RecoveryCode(user_id=user.id, code_hash=hash_password(canonical)))
    await db.commit()
    return [_display_recovery_code(code) for code in canonical_codes]


async def disable_two_factor(
    db: AsyncSession, user: User, code: str | None, recovery_code: str | None
) -> None:
    if not user.totp_enabled:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "2FA not enabled")
    verified = False
    if code:
        secret = _decrypt_totp_secret(user)
        verified = _verify_totp_code(secret, code)
    if not verified and recovery_code:
        verified = await _consume_recovery_code(db, user, recovery_code)
    if not verified:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid verification code")
    user.totp_secret_ciphertext = None
    user.totp_enabled = False
    await db.execute(delete(RecoveryCode).where(RecoveryCode.user_id == user.id))
    await db.commit()


def create_challenge_token(user_id: str) -> str:
    return create_jwt_token(user_id, "2fa", CHALLENGE_TTL)


async def verify_login_challenge(
    db: AsyncSession, challenge_token: str, code: str | None
) -> User:
    payload = decode_jwt_token(challenge_token, "2fa")
    user = await db.get(User, payload["sub"])
    if user is None or user.deleted_at is not None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid token")
    if not user.totp_enabled:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid token")
    allowed = await hit_rate_limit(
        f"rate_limit:2fa:{user.id}", VERIFY_RATE_LIMIT, VERIFY_RATE_WINDOW_SECONDS
    )
    if not allowed:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS, "Too many attempts, try again later"
        )
    if not code or not code.strip():
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid verification code")
    verified = False
    secret = _decrypt_totp_secret(user)
    if _verify_totp_code(secret, code) or await _consume_recovery_code(db, user, code):
        verified = True
    if not verified:
        await db.rollback()
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid verification code")
    await db.commit()
    return user
