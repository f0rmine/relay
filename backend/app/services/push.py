import asyncio
import json
import logging
import time
from functools import lru_cache
from pathlib import Path

import anyio
import httpx
from google.auth.transport.requests import Request
from google.oauth2 import service_account
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import get_settings
from app.core.database import AsyncSessionLocal
from app.core.redis import get_redis
from app.models.device import DeviceToken
from app.models.message import Message
from app.models.user import User

logger = logging.getLogger(__name__)

FCM_SCOPE = "https://www.googleapis.com/auth/firebase.messaging"
FCM_CONFIG_ERROR_COOLDOWN_SECONDS = 300
PUSH_QUEUE_KEY = "push:queue"
PUSH_JOB_MAX_ATTEMPTS = 3
PUSH_PREVIEW_LABELS = {
    "en": {
        "deleted": "Message deleted",
        "image": "Image",
        "attachment": "Attachment",
        "message": "Message",
    },
    "uk": {
        "deleted": "Повідомлення видалено",
        "image": "Зображення",
        "attachment": "Вкладення",
        "message": "Повідомлення",
    },
}

_fcm_config_disabled_until = 0.0
_fcm_config_lock = asyncio.Lock()
_push_tasks: set[asyncio.Task] = set()


def _push_task_finished(task: asyncio.Task) -> None:
    _push_tasks.discard(task)
    if task.cancelled():
        return
    exception = task.exception()
    if exception is not None:
        logger.error(
            "Background push task failed",
            exc_info=(type(exception), exception, exception.__traceback__),
        )


async def _send_message_push_by_id(
    recipient_ids: list[str], sender_id: str, message_id: str
) -> None:
    async with AsyncSessionLocal() as db:
        sender = await db.get(User, sender_id)
        message = (
            await db.scalars(
                select(Message)
                .where(Message.id == message_id)
                .options(selectinload(Message.attachments))
            )
        ).first()
        if sender is None or message is None:
            return
        await send_message_push(db, recipient_ids, sender, message)


def schedule_message_push(recipient_ids: list[str], sender_id: str, message_id: str) -> None:
    if not recipient_ids:
        return
    job = json.dumps(
        {"recipient_ids": recipient_ids, "sender_id": sender_id, "message_id": message_id}
    )
    task = asyncio.create_task(_enqueue_push_job(job))
    _push_tasks.add(task)
    task.add_done_callback(_push_task_finished)


async def _enqueue_push_job(job: str) -> None:
    try:
        redis = await get_redis()
        await redis.rpush(PUSH_QUEUE_KEY, job)
    except asyncio.CancelledError:
        raise
    except Exception:
        logger.exception("Failed to enqueue push notification")


async def push_queue_worker() -> None:
    while True:
        try:
            redis = await get_redis()
            item = await redis.blpop(PUSH_QUEUE_KEY, timeout=5)
            if item is None:
                continue
            raw = item[1] if isinstance(item, tuple) else item
            try:
                job = json.loads(raw)
            except (json.JSONDecodeError, TypeError):
                logger.warning("Discarding malformed push queue entry")
                continue
            await _run_push_job(job)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Push queue worker cycle failed")
            await asyncio.sleep(2)


async def _run_push_job(job: dict) -> None:
    recipient_ids = job.get("recipient_ids") or []
    sender_id = job.get("sender_id")
    message_id = job.get("message_id")
    if not recipient_ids or not sender_id or not message_id:
        return
    for attempt in range(1, PUSH_JOB_MAX_ATTEMPTS + 1):
        try:
            await _send_message_push_by_id(recipient_ids, sender_id, message_id)
            return
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception(
                "Push delivery attempt %s/%s failed", attempt, PUSH_JOB_MAX_ATTEMPTS
            )
            if attempt < PUSH_JOB_MAX_ATTEMPTS:
                await asyncio.sleep(2 * attempt)
    logger.error("Push job dropped after %s attempts", PUSH_JOB_MAX_ATTEMPTS)


async def drain_push_tasks() -> None:
    if _push_tasks:
        await asyncio.gather(*tuple(_push_tasks), return_exceptions=True)


@lru_cache
def _credentials():
    settings = get_settings()
    if not settings.firebase_service_account_file:
        return None
    return service_account.Credentials.from_service_account_file(
        settings.firebase_service_account_file,
        scopes=[FCM_SCOPE],
    )


def _refresh_access_token() -> str | None:
    credentials = _credentials()
    if credentials is None:
        return None
    credentials.refresh(Request())
    return credentials.token


async def _access_token() -> str | None:
    return await anyio.to_thread.run_sync(_refresh_access_token)


def push_preview(message: Message, locale: str = "en") -> str:
    labels = PUSH_PREVIEW_LABELS.get(locale, PUSH_PREVIEW_LABELS["en"])
    if message.deleted_at:
        return labels["deleted"]
    has_text = message.text_ciphertext is not None or message.text is not None
    attachment = message.attachments[0] if message.attachments else None
    if not has_text and attachment is not None:
        if attachment.mime_type.startswith("image/"):
            return labels["image"]
        return labels["attachment"]
    return labels["message"]


def _fcm_error_summary(response: httpx.Response) -> str:
    try:
        error = response.json().get("error", {})
    except ValueError:
        return response.text[:300]
    status = error.get("status") or "UNKNOWN"
    message = error.get("message") or "No Firebase error message"
    return f"{status}: {message}"


def _fcm_config_error_active() -> bool:
    return time.monotonic() < _fcm_config_disabled_until


def _pause_fcm_config_errors() -> bool:
    global _fcm_config_disabled_until

    if _fcm_config_error_active():
        return False
    _fcm_config_disabled_until = time.monotonic() + FCM_CONFIG_ERROR_COOLDOWN_SECONDS
    return True


def _mark_fcm_config_error(response: httpx.Response, summary: str) -> bool:
    if response.status_code != 403 or "PERMISSION_DENIED" not in summary:
        return False
    return _pause_fcm_config_errors()


def _fcm_config_missing_reason() -> str | None:
    settings = get_settings()
    if not settings.push_notifications_enabled:
        return "disabled"
    if not settings.firebase_project_id:
        return "FIREBASE_PROJECT_ID is not configured"
    service_account_file = settings.firebase_service_account_file
    if not service_account_file:
        return "FIREBASE_SERVICE_ACCOUNT_FILE is not configured"
    service_account_path = Path(service_account_file)
    if not service_account_path.exists():
        return f"service account file not found at {service_account_path}"
    return None


async def send_message_push(
    db: AsyncSession,
    recipient_ids: list[str],
    sender: User,
    message: Message,
) -> None:
    settings = get_settings()
    missing_reason = _fcm_config_missing_reason()
    if missing_reason == "disabled" or _fcm_config_error_active():
        return
    if missing_reason:
        if _pause_fcm_config_errors():
            logger.warning(
                "FCM push attempts paused for %s seconds: %s",
                FCM_CONFIG_ERROR_COOLDOWN_SECONDS,
                missing_reason,
            )
        return

    tokens = (
        await db.scalars(
            select(DeviceToken).where(
                DeviceToken.user_id.in_(recipient_ids),
                DeviceToken.enabled.is_(True),
            )
        )
    ).all()
    if not tokens:
        return

    async with _fcm_config_lock:
        if _fcm_config_error_active():
            return
        try:
            access_token = await _access_token()
        except Exception as exc:  # noqa: BLE001
            if _pause_fcm_config_errors():
                logger.warning(
                    "FCM push attempts paused for %s seconds after credential error: %s",
                    FCM_CONFIG_ERROR_COOLDOWN_SECONDS,
                    type(exc).__name__,
                )
            return
    if not access_token:
        return

    endpoint = (
        f"https://fcm.googleapis.com/v1/projects/{settings.firebase_project_id}/messages:send"
    )
    title = sender.display_name or sender.username

    async with httpx.AsyncClient(timeout=10) as client:
        for token in tokens:
            body = push_preview(message, token.locale)
            payload = {
                "message": {
                    "token": token.token,
                    "notification": {
                        "title": title,
                        "body": body,
                    },
                    "data": {
                        "conversation_id": message.conversation_id,
                        "message_id": message.id,
                        "sender_id": sender.id,
                    },
                    "android": {
                        "priority": "HIGH",
                        "notification": {
                            "channel_id": "messages",
                            "click_action": "OPEN_CHAT",
                        },
                    },
                }
            }
            try:
                response = await client.post(
                    endpoint,
                    json=payload,
                    headers={"Authorization": f"Bearer {access_token}"},
                )
                if response.status_code in {400, 404}:
                    token.enabled = False
                elif response.status_code >= 400:
                    summary = _fcm_error_summary(response)
                    logger.warning(
                        "FCM push failed: %s %s",
                        response.status_code,
                        summary,
                    )
                    if _mark_fcm_config_error(response, summary):
                        logger.warning(
                            "FCM push attempts paused for %s seconds after configuration error",
                            FCM_CONFIG_ERROR_COOLDOWN_SECONDS,
                        )
                        break
            except httpx.HTTPError:
                logger.exception("FCM push request failed")
    await db.commit()
