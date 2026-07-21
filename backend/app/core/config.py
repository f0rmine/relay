from functools import lru_cache
from pathlib import Path
from typing import Annotated, Literal
from urllib.parse import urlsplit

from pydantic import EmailStr, Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

from app.core.encryption import validate_key_configuration


class Settings(BaseSettings):
    app_name: str = "Relay Messenger"
    environment: Literal["development", "test", "production"] = "development"
    database_url: str = "postgresql+asyncpg://relay:relay_password@localhost:5432/relay"
    redis_url: str = "redis://localhost:6379/0"
    jwt_secret: str = "dev-access-secret-at-least-32-bytes-long"
    jwt_refresh_secret: str = "dev-refresh-secret-at-least-32-bytes-long"
    access_token_expire_minutes: int = Field(default=30, ge=1, le=1440)
    refresh_token_expire_days: int = Field(default=14, ge=1, le=365)
    password_reset_token_in_response: bool = False
    password_reset_email_enabled: bool = False
    password_reset_url: str = "relay://reset-password"
    smtp_host: str | None = None
    smtp_port: int = Field(default=587, ge=1, le=65535)
    smtp_username: str | None = None
    smtp_password: SecretStr | None = None
    smtp_from_address: EmailStr | None = None
    smtp_use_tls: bool = False
    smtp_starttls: bool = True
    smtp_timeout_seconds: float = Field(default=10.0, gt=0, le=60)
    cors_origins: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: ["http://localhost:5173"]
    )
    upload_dir: Path = Path("./uploads")
    max_upload_size_mb: int = Field(default=10, ge=1, le=100)
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

    @field_validator(
        "firebase_project_id",
        "firebase_service_account_file",
        "smtp_host",
        "smtp_username",
        "smtp_password",
        "smtp_from_address",
        mode="before",
    )
    @classmethod
    def empty_string_as_none(cls, value: str | Path | None) -> str | Path | None:
        if isinstance(value, str) and not value.strip():
            return None
        return value

    @field_validator("password_reset_url")
    @classmethod
    def validate_password_reset_url(cls, value: str) -> str:
        parsed = urlsplit(value)
        if not parsed.scheme or not (parsed.netloc or parsed.path):
            raise ValueError("PASSWORD_RESET_URL must be an absolute URL")
        return value

    @model_validator(mode="after")
    def validate_security_configuration(self) -> "Settings":
        validate_key_configuration(self.encryption_active_key_id, self.encryption_keys)
        if len(self.jwt_secret) < 32 or len(self.jwt_refresh_secret) < 32:
            raise ValueError("JWT secrets must contain at least 32 characters")
        if self.jwt_secret == self.jwt_refresh_secret:
            raise ValueError("JWT access and refresh secrets must be different")
        if not self.cors_origins or "*" in self.cors_origins:
            raise ValueError("CORS_ORIGINS must be a non-empty explicit allowlist")
        if self.smtp_use_tls and self.smtp_starttls:
            raise ValueError("SMTP_USE_TLS and SMTP_STARTTLS cannot both be enabled")
        if bool(self.smtp_username) != bool(self.smtp_password):
            raise ValueError("SMTP_USERNAME and SMTP_PASSWORD must be configured together")
        if self.password_reset_email_enabled and (
            not self.smtp_host or not self.smtp_from_address
        ):
            raise ValueError(
                "Enabled password reset email delivery requires SMTP_HOST and SMTP_FROM_ADDRESS"
            )
        if self.environment == "production":
            unsafe_prefixes = ("dev-", "change-me")
            if self.jwt_secret.startswith(unsafe_prefixes) or self.jwt_refresh_secret.startswith(
                unsafe_prefixes
            ):
                raise ValueError("Production JWT secrets must not use development defaults")
            if not self.database_url.startswith("postgresql+asyncpg://"):
                raise ValueError("Production DATABASE_URL must use PostgreSQL with asyncpg")
            if self.password_reset_token_in_response:
                raise ValueError("Password reset tokens cannot be exposed in production")
            if self.password_reset_email_enabled and not (self.smtp_use_tls or self.smtp_starttls):
                raise ValueError("Production password reset email delivery requires TLS or STARTTLS")
            if self.push_notifications_enabled and (
                not self.firebase_project_id or not self.firebase_service_account_file
            ):
                raise ValueError("Enabled production push notifications require Firebase settings")
        return self

    @property
    def max_upload_size_bytes(self) -> int:
        return self.max_upload_size_mb * 1024 * 1024


@lru_cache
def get_settings() -> Settings:
    return Settings()
