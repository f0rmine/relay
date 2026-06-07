from pydantic import BaseModel, Field


class DeviceTokenRegister(BaseModel):
    token: str = Field(min_length=20, max_length=500)
    platform: str = Field(default="android", max_length=20)
    device_id: str | None = Field(default=None, max_length=120)


class DeviceTokenRemove(BaseModel):
    token: str = Field(min_length=20, max_length=500)
