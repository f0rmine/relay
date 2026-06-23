import base64

import pytest
from pydantic import ValidationError

from app.core.config import Settings
from app.core.encryption import DecryptionError, ENCRYPTION_VERSION, EncryptionKeyring
from app.models.attachment import Attachment
from app.models.message import Message
from app.services.attachments import read_attachment_bytes
from app.services.messages import plaintext_message_text


def encoded_key(value: int) -> str:
    return base64.b64encode(bytes([value]) * 32).decode()


def test_encryption_settings_require_an_active_key() -> None:
    with pytest.raises(ValidationError, match="ENCRYPTION_ACTIVE_KEY_ID is required"):
        Settings(
            _env_file=None,
            encryption_active_key_id="",
            encryption_keys={},
        )


def test_encryption_settings_reject_wrong_size_key() -> None:
    short_key = base64.b64encode(b"too short").decode()

    with pytest.raises(ValidationError, match="must decode to 32 bytes"):
        Settings(
            _env_file=None,
            encryption_active_key_id="v1",
            encryption_keys={"v1": short_key},
        )


def test_encryption_settings_reject_invalid_base64_and_unknown_active_key() -> None:
    with pytest.raises(ValidationError, match="must be valid base64"):
        Settings(
            _env_file=None,
            encryption_active_key_id="v1",
            encryption_keys={"v1": "not-base64"},
        )

    with pytest.raises(ValidationError, match="must reference a key"):
        Settings(
            _env_file=None,
            encryption_active_key_id="missing",
            encryption_keys={"v1": encoded_key(1)},
        )


def test_aes_gcm_uses_unique_nonces_and_detects_wrong_key() -> None:
    keyring = EncryptionKeyring("v1", {"v1": encoded_key(1)})
    first = keyring.encrypt(b"same plaintext", associated_data=b"message-1")
    second = keyring.encrypt(b"same plaintext", associated_data=b"message-1")

    assert first.nonce != second.nonce
    assert first.ciphertext != second.ciphertext
    assert first.version == ENCRYPTION_VERSION
    assert keyring.decrypt(
        first.ciphertext,
        first.nonce,
        first.key_id,
        associated_data=b"message-1",
    ) == b"same plaintext"

    wrong_keyring = EncryptionKeyring("v1", {"v1": encoded_key(2)})
    with pytest.raises(DecryptionError, match="Invalid encrypted payload"):
        wrong_keyring.decrypt(
            first.ciphertext,
            first.nonce,
            first.key_id,
            associated_data=b"message-1",
        )

    with pytest.raises(DecryptionError, match="unavailable key"):
        keyring.decrypt(
            first.ciphertext,
            first.nonce,
            "removed-key",
            associated_data=b"message-1",
        )


def test_old_key_remains_available_after_rotation() -> None:
    old_key = encoded_key(3)
    new_key = encoded_key(4)
    before_rotation = EncryptionKeyring("old", {"old": old_key})
    encrypted = before_rotation.encrypt(b"pre-rotation", associated_data=b"attachment-1")

    after_rotation = EncryptionKeyring("new", {"old": old_key, "new": new_key})

    assert after_rotation.decrypt(
        encrypted.ciphertext,
        encrypted.nonce,
        encrypted.key_id,
        associated_data=b"attachment-1",
    ) == b"pre-rotation"
    assert after_rotation.encrypt(b"post-rotation", associated_data=b"attachment-2").key_id == "new"


def test_legacy_plaintext_message_is_still_readable() -> None:
    message = Message(id="legacy-message", text="legacy text")

    assert plaintext_message_text(message) == "legacy text"


async def test_legacy_plaintext_attachment_is_still_readable(tmp_path) -> None:
    path = tmp_path / "legacy.txt"
    path.write_bytes(b"legacy attachment")
    attachment = Attachment(
        id="legacy-attachment",
        uploader_id="legacy-user",
        original_filename="legacy.txt",
        stored_filename="legacy.txt",
        mime_type="text/plain",
        file_size=17,
        storage_path=str(path),
        public_url="/attachments/legacy-attachment/download",
    )

    assert await read_attachment_bytes(attachment) == b"legacy attachment"
