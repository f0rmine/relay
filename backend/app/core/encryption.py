import base64
import binascii
import secrets
from dataclasses import dataclass
from functools import lru_cache

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

AES_256_KEY_BYTES = 32
AES_GCM_NONCE_BYTES = 12
ENCRYPTION_VERSION = 1


class EncryptionConfigurationError(ValueError):
    pass


class DecryptionError(ValueError):
    pass


@dataclass(frozen=True)
class EncryptedPayload:
    ciphertext: bytes
    nonce: bytes
    key_id: str
    version: int = ENCRYPTION_VERSION


def _decode_key(key_id: str, encoded_key: str) -> bytes:
    try:
        key = base64.b64decode(encoded_key, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise EncryptionConfigurationError(
            f"Encryption key {key_id!r} must be valid base64"
        ) from exc
    if len(key) != AES_256_KEY_BYTES:
        raise EncryptionConfigurationError(
            f"Encryption key {key_id!r} must decode to {AES_256_KEY_BYTES} bytes"
        )
    return key


def validate_key_configuration(active_key_id: str, keys: dict[str, str]) -> None:
    if not active_key_id:
        raise EncryptionConfigurationError("ENCRYPTION_ACTIVE_KEY_ID is required")
    if not keys:
        raise EncryptionConfigurationError("ENCRYPTION_KEYS must contain at least one key")
    if active_key_id not in keys:
        raise EncryptionConfigurationError(
            "ENCRYPTION_ACTIVE_KEY_ID must reference a key in ENCRYPTION_KEYS"
        )
    for key_id, encoded_key in keys.items():
        if not key_id or len(key_id) > 100:
            raise EncryptionConfigurationError(
                "Encryption key IDs must contain between 1 and 100 characters"
            )
        _decode_key(key_id, encoded_key)


class EncryptionKeyring:
    def __init__(self, active_key_id: str, encoded_keys: dict[str, str]) -> None:
        validate_key_configuration(active_key_id, encoded_keys)
        self.active_key_id = active_key_id
        self._keys = {
            key_id: AESGCM(_decode_key(key_id, encoded_key))
            for key_id, encoded_key in encoded_keys.items()
        }

    def encrypt(self, plaintext: bytes, *, associated_data: bytes) -> EncryptedPayload:
        nonce = secrets.token_bytes(AES_GCM_NONCE_BYTES)
        ciphertext = self._keys[self.active_key_id].encrypt(nonce, plaintext, associated_data)
        return EncryptedPayload(ciphertext, nonce, self.active_key_id)

    def decrypt(
        self,
        ciphertext: bytes,
        nonce: bytes,
        key_id: str,
        *,
        associated_data: bytes,
    ) -> bytes:
        if len(nonce) != AES_GCM_NONCE_BYTES:
            raise DecryptionError("Invalid encrypted payload")
        cipher = self._keys.get(key_id)
        if cipher is None:
            raise DecryptionError("Encrypted payload references an unavailable key")
        try:
            return cipher.decrypt(nonce, ciphertext, associated_data)
        except (InvalidTag, ValueError) as exc:
            raise DecryptionError("Invalid encrypted payload") from exc


@lru_cache
def get_encryption_keyring() -> EncryptionKeyring:
    from app.core.config import get_settings

    settings = get_settings()
    return EncryptionKeyring(settings.encryption_active_key_id, settings.encryption_keys)


def message_text_associated_data(message_id: str) -> bytes:
    return f"relay:message:{message_id}:text:v1".encode()


def attachment_associated_data(attachment_id: str) -> bytes:
    return f"relay:attachment:{attachment_id}:bytes:v1".encode()
