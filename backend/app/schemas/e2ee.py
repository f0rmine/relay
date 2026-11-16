from datetime import datetime

from pydantic import BaseModel, Field

# Base64url lengths: 32 bytes -> 43 chars, 64 bytes -> 86, 1184 bytes -> 1579.
KEY_32 = Field(min_length=43, max_length=43)
SIG_64 = Field(min_length=86, max_length=86)
MLKEM_KEY = Field(min_length=1579, max_length=1579)
KEY_ID = Field(ge=0, le=0xFFFFFFFF)

MAX_EC_PREKEYS_PER_UPLOAD = 100
MAX_KEM_PREKEYS_PER_UPLOAD = 50


class IdentityPut(BaseModel):
    identity_key: str = KEY_32
    # Replacing an existing identity revokes every device and makes contacts see
    # a safety-number change, so it requires the account password.
    replace: bool = False
    password: str | None = Field(default=None, max_length=128)


class IdentityOut(BaseModel):
    identity_key: str
    revoked_devices: int = 0


class SignedPrekeyIn(BaseModel):
    key_id: int = KEY_ID
    public_key: str = KEY_32
    signature: str = SIG_64


class PqPrekeyIn(BaseModel):
    key_id: int = KEY_ID
    public_key: str = MLKEM_KEY
    signature: str = SIG_64


class OneTimePrekeyIn(BaseModel):
    key_id: int = KEY_ID
    public_key: str = KEY_32


class DeviceRegister(BaseModel):
    device_id: str = Field(min_length=8, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")
    label: str | None = Field(default=None, max_length=120)
    signing_key: str = KEY_32
    agreement_key: str = KEY_32
    identity_signature: str = SIG_64
    signed_prekey: SignedPrekeyIn
    pq_prekey: PqPrekeyIn
    one_time_prekeys: list[OneTimePrekeyIn] = Field(
        default_factory=list, max_length=MAX_EC_PREKEYS_PER_UPLOAD
    )
    pq_one_time_prekeys: list[PqPrekeyIn] = Field(
        default_factory=list, max_length=MAX_KEM_PREKEYS_PER_UPLOAD
    )


class PrekeyUpload(BaseModel):
    signed_prekey: SignedPrekeyIn | None = None
    pq_prekey: PqPrekeyIn | None = None
    one_time_prekeys: list[OneTimePrekeyIn] = Field(
        default_factory=list, max_length=MAX_EC_PREKEYS_PER_UPLOAD
    )
    pq_one_time_prekeys: list[PqPrekeyIn] = Field(
        default_factory=list, max_length=MAX_KEM_PREKEYS_PER_UPLOAD
    )


class PrekeyCounts(BaseModel):
    one_time_prekeys: int
    pq_one_time_prekeys: int


class SignedPrekeyOut(BaseModel):
    key_id: int
    public_key: str
    signature: str


class PqPrekeyOut(BaseModel):
    key_id: int
    public_key: str
    signature: str


class OneTimePrekeyOut(BaseModel):
    key_id: int
    public_key: str


class DeviceOut(BaseModel):
    device_id: str
    signing_key: str
    agreement_key: str
    identity_signature: str
    signed_prekey: SignedPrekeyOut
    pq_prekey: PqPrekeyOut
    created_at: datetime
    # Only returned to the device owner: labels like "Pixel 8" are metadata.
    label: str | None = None


class OwnDeviceOut(DeviceOut):
    last_seen_at: datetime | None = None
    prekeys: PrekeyCounts


class UserKeysOut(BaseModel):
    user_id: str
    identity_key: str
    devices: list[DeviceOut]


class ClaimedBundleOut(BaseModel):
    user_id: str
    identity_key: str
    device: DeviceOut
    # None when exhausted: the session then relies on the signed / last-resort keys.
    one_time_prekey: OneTimePrekeyOut | None = None
    pq_one_time_prekey: PqPrekeyOut | None = None
