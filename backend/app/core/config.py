from functools import lru_cache
from pathlib import Path
from typing import Annotated

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

from app.core.encryption import validate_key_configuration


class Settings(BaseSettings):
    app_name: str = "Relay Messenger"
    environment: str = "development"
    database_url: str = "postgresql+asyncpg://relay:relay_password@localhost:5432/relay"
    redis_url: str = "redis://localhost:6379/0"
    jwt_secret: str = "dev-access-secret-at-least-32-bytes-long"
    jwt_refresh_secret: str = "dev-refresh-secret-at-least-32-bytes-long"
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 14
    cors_origins: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: ["http://localhost:5173"]
    )
    upload_dir: Path = Path("./uploads")
    max_upload_size_mb: int = 10
    encryption_active_key_id: str = ""
    encryption_keys: dict[str, str] = Field(default_factory=dict)
    firebase_project_id: str | None = None
    firebase_service_account_file: Path | None = None
    push_notifications_enabled: bool = False

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    @field_validator("cors_origins", mode="before")
    @classmethod
    def parse_cors_origins(cls, value: str | list[str]) -> list[str]:
        if isinstance(value, str):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value

    @field_validator("firebase_project_id", "firebase_service_account_file", mode="before")
    @classmethod
    def empty_string_as_none(cls, value: str | Path | None) -> str | Path | None:
        if isinstance(value, str) and not value.strip():
            return None
        return value

    @model_validator(mode="after")
    def validate_encryption(self) -> "Settings":
        validate_key_configuration(self.encryption_active_key_id, self.encryption_keys)
        return self

    @property
    def max_upload_size_bytes(self) -> int:
        return self.max_upload_size_mb * 1024 * 1024


@lru_cache
def get_settings() -> Settings:
    return Settings()
