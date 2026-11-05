import hashlib
import hmac
import secrets
import time
from datetime import UTC, datetime, timedelta
from typing import Any, Literal
from uuid import uuid4

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from fastapi import HTTPException, status

from app.core.config import get_settings

settings = get_settings()
password_hasher = PasswordHasher()

TokenType = Literal["access", "refresh", "password_reset", "2fa"]


def hash_password(password: str) -> str:
    return password_hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return password_hasher.verify(password_hash, password)
    except VerifyMismatchError:
        return False
    except Exception:  # noqa: BLE001
        return False


def hash_token(token: str) -> str:
    return password_hasher.hash(token)


def verify_token_hash(token: str, token_hash: str) -> bool:
    return verify_password(token, token_hash)


AVATAR_LINK_TTL_SECONDS = 7 * 24 * 3600
AVATAR_URL_PREFIX = "/uploads/avatars/"


def _avatar_signature(path: str, exp: int) -> str:
    return hmac.new(
        settings.jwt_secret.encode(), f"{path}:{exp}".encode(), hashlib.sha256
    ).hexdigest()


def sign_avatar_url(url: str | None) -> str | None:
    if not url or not url.startswith(AVATAR_URL_PREFIX) or "sig=" in url:
        return url
    exp = int(time.time()) + AVATAR_LINK_TTL_SECONDS
    sig = _avatar_signature(url.split("?")[0], exp)
    return f"{url}?exp={exp}&sig={sig}"


def verify_avatar_url(url: str, exp: int, sig: str) -> bool:
    if not url.startswith(AVATAR_URL_PREFIX) or exp < time.time():
        return False
    return secrets.compare_digest(_avatar_signature(url, exp), sig)


def _secret_for(token_type: TokenType) -> str:
    return settings.jwt_refresh_secret if token_type in {"refresh", "password_reset"} else settings.jwt_secret


def create_jwt_token(
    subject: str,
    token_type: TokenType,
    expires_delta: timedelta,
    extra: dict[str, Any] | None = None,
) -> str:
    now = datetime.now(UTC)
    payload: dict[str, Any] = {
        "sub": subject,
        "type": token_type,
        "iat": int(now.timestamp()),
        "exp": int((now + expires_delta).timestamp()),
        "jti": str(uuid4()),
    }
    if extra:
        payload.update(extra)
    return jwt.encode(payload, _secret_for(token_type), algorithm="HS256")


def decode_jwt_token(token: str, expected_type: TokenType) -> dict[str, Any]:
    try:
        payload = jwt.decode(token, _secret_for(expected_type), algorithms=["HS256"])
    except jwt.ExpiredSignatureError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Token expired") from exc
    except jwt.InvalidTokenError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid token") from exc
    if payload.get("type") != expected_type:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid token type")
    return payload
