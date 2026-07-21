import asyncio
import logging
import smtplib
import ssl
from email.message import EmailMessage
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from app.core.config import Settings, get_settings

logger = logging.getLogger(__name__)


def build_password_reset_url(base_url: str, token: str) -> str:
    parsed = urlsplit(base_url)
    query = parse_qsl(parsed.query, keep_blank_values=True)
    query.append(("token", token))
    return urlunsplit(parsed._replace(query=urlencode(query)))


def _build_password_reset_message(settings: Settings, recipient: str, token: str) -> EmailMessage:
    message = EmailMessage()
    message["Subject"] = "Reset your Relay password"
    message["From"] = str(settings.smtp_from_address)
    message["To"] = recipient
    reset_url = build_password_reset_url(settings.password_reset_url, token)
    message.set_content(
        "A password reset was requested for your Relay account.\n\n"
        f"Open this link to choose a new password:\n{reset_url}\n\n"
        f"If the link does not open the Relay client, paste this reset token:\n{token}\n\n"
        "This link expires in one hour. If you did not request this, you can ignore this email."
    )
    return message


def _send_message(settings: Settings, message: EmailMessage) -> None:
    if settings.smtp_host is None:
        raise RuntimeError("SMTP is not configured")

    context = ssl.create_default_context()
    smtp_class = smtplib.SMTP_SSL if settings.smtp_use_tls else smtplib.SMTP
    smtp_kwargs: dict = {
        "host": settings.smtp_host,
        "port": settings.smtp_port,
        "timeout": settings.smtp_timeout_seconds,
    }
    if settings.smtp_use_tls:
        smtp_kwargs["context"] = context

    with smtp_class(**smtp_kwargs) as smtp:
        if settings.smtp_starttls:
            smtp.starttls(context=context)
        if settings.smtp_username is not None and settings.smtp_password is not None:
            smtp.login(settings.smtp_username, settings.smtp_password.get_secret_value())
        smtp.send_message(message)


async def send_password_reset_email(recipient: str, token: str) -> None:
    settings = get_settings()
    if not settings.password_reset_email_enabled:
        return
    message = _build_password_reset_message(settings, recipient, token)
    await asyncio.to_thread(_send_message, settings, message)


async def deliver_password_reset_email(recipient: str, token: str) -> None:
    try:
        await send_password_reset_email(recipient, token)
    except Exception as exc:
        # Do not leak the reset token, recipient, SMTP response, or credentials to logs.
        logger.warning("Password reset email delivery failed (%s)", type(exc).__name__)
