import logging
from email.message import EmailMessage

import pytest

from app.core.config import Settings
from app.services import mail


def mail_settings(**overrides) -> Settings:
    values = {
        "_env_file": None,
        "environment": "test",
        "encryption_active_key_id": "test-v1",
        "encryption_keys": {
            "test-v1": "AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8="
        },
        "password_reset_email_enabled": True,
        "password_reset_url": "https://relay.example.com/reset?source=email",
        "smtp_host": "smtp.example.com",
        "smtp_port": 587,
        "smtp_username": "relay",
        "smtp_password": "smtp-secret",
        "smtp_from_address": "no-reply@example.com",
        "smtp_starttls": True,
    }
    values.update(overrides)
    return Settings(**values)


def test_password_reset_url_preserves_existing_query_and_encodes_token() -> None:
    reset_url = mail.build_password_reset_url(
        "https://relay.example.com/reset?source=email", "token with + and /"
    )

    assert reset_url == (
        "https://relay.example.com/reset?source=email&token=token+with+%2B+and+%2F"
    )


async def test_password_reset_email_uses_starttls_and_authentication(monkeypatch) -> None:
    settings = mail_settings()
    sent: list[EmailMessage] = []
    actions: list[str] = []

    class FakeSMTP:
        def __init__(self, **kwargs) -> None:
            assert kwargs["host"] == "smtp.example.com"
            assert kwargs["port"] == 587
            assert kwargs["timeout"] == 10.0

        def __enter__(self):
            return self

        def __exit__(self, *args) -> None:
            return None

        def starttls(self, *, context) -> None:
            assert context is not None
            actions.append("starttls")

        def login(self, username: str, password: str) -> None:
            assert (username, password) == ("relay", "smtp-secret")
            actions.append("login")

        def send_message(self, message: EmailMessage) -> None:
            sent.append(message)

    monkeypatch.setattr(mail, "get_settings", lambda: settings)
    monkeypatch.setattr(mail.smtplib, "SMTP", FakeSMTP)

    await mail.send_password_reset_email("alice@example.com", "reset-token")

    assert actions == ["starttls", "login"]
    assert len(sent) == 1
    assert sent[0]["To"] == "alice@example.com"
    assert sent[0]["From"] == "no-reply@example.com"
    assert "token=reset-token" in sent[0].get_content()


async def test_delivery_failure_is_swallowed_and_sensitive_values_are_not_logged(
    monkeypatch, caplog
) -> None:
    reset_token = "sensitive-reset-token"
    smtp_secret = "sensitive-smtp-password"

    async def fail_delivery(recipient: str, token: str) -> None:
        raise RuntimeError(f"failed for {recipient} with {token} and {smtp_secret}")

    monkeypatch.setattr(mail, "send_password_reset_email", fail_delivery)
    with caplog.at_level(logging.WARNING, logger=mail.__name__):
        await mail.deliver_password_reset_email("alice@example.com", reset_token)

    assert "Password reset email delivery failed (RuntimeError)" in caplog.text
    assert "alice@example.com" not in caplog.text
    assert reset_token not in caplog.text
    assert smtp_secret not in caplog.text


@pytest.mark.parametrize("known_account", [True, False])
async def test_forgot_password_response_is_enumeration_safe(
    client, monkeypatch, known_account: bool
) -> None:
    from types import SimpleNamespace

    from app.api.routes import auth as auth_route
    from app.tests.conftest import register

    if known_account:
        await register(client, "alice", "alice@example.com")
    delivered: list[tuple[str, str]] = []

    async def capture_delivery(recipient: str, token: str) -> None:
        delivered.append((recipient, token))

    monkeypatch.setattr(
        auth_route,
        "get_settings",
        lambda: SimpleNamespace(password_reset_token_in_response=False),
    )
    monkeypatch.setattr(auth_route, "deliver_password_reset_email", capture_delivery)

    response = await client.post("/auth/forgot-password", json={"email": "alice@example.com"})

    assert response.status_code == 200
    assert response.json() == {
        "detail": "If the email exists, password reset instructions will be sent.",
        "reset_token": None,
    }
    assert len(delivered) == int(known_account)
    if delivered:
        assert delivered[0][0] == "alice@example.com"
        assert delivered[0][1]
