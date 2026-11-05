from pydantic import BaseModel, EmailStr, Field, field_validator, model_validator

from app.schemas.user import UserPublic


class RegisterRequest(BaseModel):
    username: str = Field(min_length=3, max_length=32, pattern=r"^[a-zA-Z0-9_]+$")
    display_name: str = Field(min_length=1, max_length=80)
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)

    @field_validator("display_name")
    @classmethod
    def normalize_display_name(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Display name is required")
        return normalized


class LoginRequest(BaseModel):
    login: str = Field(min_length=3, max_length=255, description="Username or email")
    password: str = Field(min_length=1, max_length=128)


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user: UserPublic


class RefreshRequest(BaseModel):
    refresh_token: str


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ForgotPasswordResponse(BaseModel):
    detail: str
    reset_token: str | None = None


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str = Field(min_length=8, max_length=128)


class LogoutRequest(BaseModel):
    refresh_token: str | None = None


class TwoFactorSetupResponse(BaseModel):
    secret: str
    otpauth_url: str


class TwoFactorEnableRequest(BaseModel):
    code: str = Field(min_length=1, max_length=20)


class TwoFactorEnableResponse(BaseModel):
    recovery_codes: list[str]


class TwoFactorDisableRequest(BaseModel):
    code: str | None = Field(default=None, max_length=20)
    recovery_code: str | None = Field(default=None, max_length=20)

    @field_validator("code", "recovery_code", mode="before")
    @classmethod
    def _empty_as_none(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            return None
        return value

    @model_validator(mode="after")
    def _require_code_or_recovery_code(self) -> "TwoFactorDisableRequest":
        if not self.code and not self.recovery_code:
            raise ValueError("code or recovery_code is required")
        return self


class LoginVerifyRequest(BaseModel):
    challenge_token: str = Field(min_length=1)
    code: str = Field(min_length=1, max_length=20)


class LoginChallengeResponse(BaseModel):
    requires_2fa: bool = True
    challenge_token: str


class AccountDeleteRequest(BaseModel):
    confirmation: str

    @field_validator("confirmation")
    @classmethod
    def _must_be_delete(cls, value: str) -> str:
        if value != "DELETE":
            raise ValueError("confirmation must be DELETE")
        return value
