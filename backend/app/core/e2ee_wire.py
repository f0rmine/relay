"""Canonical encodings and signature checks for the E2EE key directory.

These byte layouts are part of the protocol: the mobile client builds the exact
same messages (mobile/src/crypto/wire.ts) and shared test vectors pin them.
Every signed message starts with a distinct domain-separation label so a
signature made for one purpose can never be replayed as another.
"""

from __future__ import annotations

import base64
import binascii
import struct

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

ED25519_KEY_BYTES = 32
ED25519_SIG_BYTES = 64
X25519_KEY_BYTES = 32
MLKEM768_PUBLIC_KEY_BYTES = 1184

DEVICE_LABEL = b"relay-e2ee-v1/device\x00"
SIGNED_PREKEY_LABEL = b"relay-e2ee-v1/spk\x00"
PQ_PREKEY_LABEL = b"relay-e2ee-v1/pqpk\x00"


class WireError(ValueError):
    """Raised for malformed keys or signatures that fail verification."""


def b64decode(value: str, expected_len: int, what: str) -> bytes:
    """Decode unpadded base64url and enforce an exact length."""
    if not isinstance(value, str) or not value or "=" in value:
        raise WireError(f"{what}: expected unpadded base64url")
    try:
        raw = base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))
    except (binascii.Error, ValueError) as exc:
        raise WireError(f"{what}: invalid base64url") from exc
    if b64encode(raw) != value:
        raise WireError(f"{what}: non-canonical base64url")
    if len(raw) != expected_len:
        raise WireError(f"{what}: expected {expected_len} bytes, got {len(raw)}")
    return raw


def b64encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _text(value: str) -> bytes:
    encoded = value.encode("utf-8")
    if b"\x00" in encoded:
        raise WireError("identifiers must not contain NUL")
    return encoded


def device_message(user_id: str, device_id: str, signing_key: bytes, agreement_key: bytes) -> bytes:
    """What the account identity key signs to vouch for a device."""
    return (
        DEVICE_LABEL
        + _text(user_id)
        + b"\x00"
        + _text(device_id)
        + b"\x00"
        + signing_key
        + agreement_key
    )


def prekey_message(label: bytes, device_id: str, key_id: int, public_key: bytes) -> bytes:
    """What a device signing key signs for a signed or post-quantum prekey."""
    if not 0 <= key_id <= 0xFFFFFFFF:
        raise WireError("key_id out of range")
    return label + _text(device_id) + b"\x00" + struct.pack(">I", key_id) + public_key


def verify(public_key: bytes, signature: bytes, message: bytes, what: str) -> None:
    try:
        Ed25519PublicKey.from_public_bytes(public_key).verify(signature, message)
    except (InvalidSignature, ValueError) as exc:
        raise WireError(f"{what}: signature verification failed") from exc
