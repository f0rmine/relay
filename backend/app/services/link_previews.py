"""SSRF-guarded Open Graph link previews.

Preview images are returned as external ``image_url`` only; no image bytes are
stored as Attachments. This keeps the attachment-encryption pipeline out of
scope for link preview caching (documented tradeoff).
"""

import asyncio
import html.parser
import ipaddress
import logging
import re
from urllib.parse import urlsplit

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import AsyncSessionLocal
from app.core.redis import get_redis
from app.models.link_preview import LinkPreview
from app.models.message import Message
from app.services.conversations import require_participant
from app.websocket.events import conversation_participant_ids, serialize_message
from app.websocket.manager import manager

logger = logging.getLogger(__name__)

MAX_HTML_BYTES = 512 * 1024
MAX_URL_LENGTH = 2000
FETCH_TIMEOUT_SECONDS = 5
_URL_RE = re.compile(r"https?://[^\s<>\"')\]]+", re.IGNORECASE)
_TRAILING_PUNCT = ").,;!?:\"'"


def extract_first_url(text: str | None) -> str | None:
    if not text:
        return None
    match = _URL_RE.search(text)
    if not match:
        return None
    url = match.group(0).rstrip(_TRAILING_PUNCT)
    if len(url) > MAX_URL_LENGTH:
        url = url[:MAX_URL_LENGTH]
    return url


def _is_blocked_ip(value: str) -> bool:
    try:
        ip = ipaddress.ip_address(value)
    except ValueError:
        return True
    return (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
        or ip in ipaddress.ip_network("127.0.0.0/8")
        or ip in ipaddress.ip_network("169.254.0.0/16")
        or ip in ipaddress.ip_network("10.0.0.0/8")
        or ip in ipaddress.ip_network("192.168.0.0/16")
        or ip in ipaddress.ip_network("172.16.0.0/12")
        or ip in ipaddress.ip_network("::1/128")
        or ip in ipaddress.ip_network("fe80::/10")
        or ip in ipaddress.ip_network("fc00::/7")
    )


async def _validate_public_url(url: str) -> bool:
    parsed = urlsplit(url)
    if parsed.scheme not in {"http", "https"}:
        return False
    host = parsed.hostname
    if not host:
        return False
    # IP literal: check directly.
    try:
        ipaddress.ip_address(host)
        return not _is_blocked_ip(host)
    except ValueError:
        pass
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    try:
        infos = await asyncio.get_running_loop().getaddrinfo(host, port)
    except OSError:
        return False
    if not infos:
        return False
    for info in infos:
        sockaddr = info[4]
        candidate = sockaddr[0] if sockaddr else ""
        if _is_blocked_ip(candidate):
            return False
    return True


class _OgParser(html.parser.HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.og: dict[str, str] = {}
        self._title_parts: list[str] = []
        self._in_title = False

    def handle_starttag(self, tag: str, attrs: list) -> None:  # type: ignore[override]
        attr_dict = dict(attrs)
        if tag == "meta":
            key = (attr_dict.get("property") or attr_dict.get("name") or "").lower()
            if key.startswith("og:") and attr_dict.get("content"):
                self.og[key[3:]] = attr_dict["content"].strip()
        elif tag == "title":
            self._in_title = True

    def handle_endtag(self, tag: str) -> None:
        if tag == "title":
            self._in_title = False

    def handle_data(self, data: str) -> None:
        if self._in_title:
            self._title_parts.append(data)


def parse_open_graph(html_text: str) -> tuple[str | None, str | None, str | None]:
    parser = _OgParser()
    try:
        parser.feed(html_text)
    except Exception:
        logger.debug("Open Graph parse failed", exc_info=True)
    title = (parser.og.get("title") or "".join(parser._title_parts).strip() or None)
    description = parser.og.get("description") or parser.og.get("og:description")
    image_url = parser.og.get("image") or parser.og.get("image:url")
    if title and len(title) > 500:
        title = title[:500]
    if description and len(description) > 10000:
        description = description[:10000]
    if image_url and len(image_url) > MAX_URL_LENGTH:
        image_url = image_url[:MAX_URL_LENGTH]
    return title, description, image_url


async def _fetch_html(url: str) -> str | None:
    """Fetch up to MAX_HTML_BYTES of HTML. Returns decoded text or None."""
    if not await _validate_public_url(url):
        logger.info("Link preview fetch blocked for unsafe URL %s", url)
        return None
    current = url
    timeout = httpx.Timeout(FETCH_TIMEOUT_SECONDS, connect=FETCH_TIMEOUT_SECONDS)
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=False, max_redirects=3) as client:
        for _redirect in range(4):
            if not await _validate_public_url(current):
                return None
            response = await client.get(current, headers={"User-Agent": "Relay-link-preview/1.0"})
            if response.is_redirect or response.status_code in {301, 302, 303, 307, 308}:
                location = response.headers.get("location")
                if not location:
                    return None
                # Resolve relative redirect.
                from urllib.parse import urljoin

                current = urljoin(current, location)
                continue
            if response.status_code >= 400:
                return None
            content_length = response.headers.get("content-length")
            if content_length and content_length.isdigit() and int(content_length) > MAX_HTML_BYTES:
                return None
            chunks: list[bytes] = []
            total = 0
            async for chunk in response.aiter_bytes():
                total += len(chunk)
                if total > MAX_HTML_BYTES:
                    return None
                chunks.append(chunk)
            raw = b"".join(chunks)
            encoding = response.encoding or "utf-8"
            try:
                return raw.decode(encoding, errors="replace")
            except (LookupError, UnicodeDecodeError):
                return raw.decode("utf-8", errors="replace")
    return None


def serialize_preview(preview: LinkPreview | None) -> dict | None:
    if preview is None:
        return None
    return {
        "url": preview.url,
        "title": preview.title,
        "description": preview.description,
        "image_url": preview.image_url,
    }


async def _store_preview(
    url: str, title: str | None, description: str | None, image_url: str | None, db: AsyncSession
) -> LinkPreview | None:
    existing = (
        await db.scalars(select(LinkPreview).where(LinkPreview.url == url))
    ).first()
    if existing is not None:
        return existing
    preview = LinkPreview(url=url, title=title, description=description, image_url=image_url)
    db.add(preview)
    try:
        await db.commit()
        await db.refresh(preview)
        return preview
    except Exception:  # noqa: BLE001
        await db.rollback()
        return (
            await db.scalars(select(LinkPreview).where(LinkPreview.url == url))
        ).first()


async def _fetch_and_store(url: str, db: AsyncSession | None = None) -> LinkPreview | None:
    html_text = await _fetch_html(url)
    if html_text is None:
        return None
    title, description, image_url = parse_open_graph(html_text)
    if db is None:
        async with AsyncSessionLocal() as session:
            return await _store_preview(url, title, description, image_url, session)
    return await _store_preview(url, title, description, image_url, db)


async def get_cached_preview(db: AsyncSession, url: str) -> LinkPreview | None:
    return (
        await db.scalars(select(LinkPreview).where(LinkPreview.url == url))
    ).first()


async def get_or_fetch_preview(db: AsyncSession, url: str) -> LinkPreview | None:
    cached = await get_cached_preview(db, url)
    if cached is not None:
        return cached
    return await _fetch_and_store(url, db)


async def process_message_link_preview(
    message_id: str, url: str, db: AsyncSession | None = None
) -> None:
    """Fetch preview for a message URL and broadcast message:updated."""
    try:
        if db is None:
            async with AsyncSessionLocal() as session:
                await process_message_link_preview(message_id, url, session)
            return
        preview = await _fetch_and_store(url, db)
        if preview is None:
            return
        # Re-load with full relations for serialization.
        from sqlalchemy.orm import selectinload

        refreshed = (
            await db.scalars(
                select(Message)
                .options(
                    selectinload(Message.attachments),
                    selectinload(Message.reads),
                    selectinload(Message.reactions),
                    selectinload(Message.reply_to),
                )
                .where(Message.id == message_id)
            )
        ).first()
        if refreshed is None or refreshed.deleted_at is not None:
            return
        refreshed._link_preview = serialize_preview(preview)  # type: ignore[attr-defined]
        conversation = await require_participant(db, refreshed.conversation_id, refreshed.sender_id)
        participants = await conversation_participant_ids(conversation)
        redis = await get_redis()
        await manager.broadcast_to_users(
            redis, participants, "message:updated", serialize_message(refreshed)
        )
    except asyncio.CancelledError:
        raise
    except Exception:
        logger.exception("Link preview processing failed for message %s", message_id)


_tasks: set[asyncio.Task] = set()


def _task_done(task: asyncio.Task) -> None:
    _tasks.discard(task)
    if task.cancelled():
        return
    exc = task.exception()
    if exc is not None:
        logger.error("Link preview task failed", exc_info=(type(exc), exc, exc.__traceback__))


def schedule_preview_for_text(message_id: str, text: str | None) -> None:
    url = extract_first_url(text)
    if not url:
        return
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return
    task = loop.create_task(process_message_link_preview(message_id, url))
    _tasks.add(task)
    task.add_done_callback(_task_done)
