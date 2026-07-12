import base64

import pytest
from pydantic import ValidationError

from app.core.config import Settings


def encoded_key() -> str:
    return base64.b64encode(bytes(range(32))).decode()


def settings_kwargs() -> dict:
    return {
        "_env_file": None,
        "encryption_active_key_id": "v1",
        "encryption_keys": {"v1": encoded_key()},
    }


def test_security_settings_reject_weak_or_shared_jwt_secrets() -> None:
    with pytest.raises(ValidationError, match="at least 32 characters"):
        Settings(**settings_kwargs(), jwt_secret="short")

    shared = "shared-secret-that-is-longer-than-32-characters"
    with pytest.raises(ValidationError, match="must be different"):
        Settings(**settings_kwargs(), jwt_secret=shared, jwt_refresh_secret=shared)


def test_production_settings_reject_debug_reset_tokens_and_defaults() -> None:
    with pytest.raises(ValidationError, match="development defaults"):
        Settings(
            **settings_kwargs(),
            environment="production",
            jwt_secret="dev-access-secret-at-least-32-bytes-long",
            jwt_refresh_secret="dev-refresh-secret-at-least-32-bytes-long",
        )

    production = {
        **settings_kwargs(),
        "environment": "production",
        "database_url": "postgresql+asyncpg://relay:secret@postgres:5432/relay",
        "jwt_secret": "production-access-secret-with-at-least-32-characters",
        "jwt_refresh_secret": "production-refresh-secret-with-at-least-32-characters",
        "cors_origins": ["https://relay.example.com"],
        "password_reset_token_in_response": False,
    }
    with pytest.raises(ValidationError, match="cannot be exposed"):
        Settings(**{**production, "password_reset_token_in_response": True})

    assert Settings(**production).environment == "production"


def test_cors_settings_require_an_explicit_allowlist() -> None:
    with pytest.raises(ValidationError, match="explicit allowlist"):
        Settings(**settings_kwargs(), cors_origins=["*"])
