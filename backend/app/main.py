import asyncio
import logging
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.api.routes import (
    attachments,
    auth,
    conversations,
    devices,
    messages,
    search,
    users,
)
from app.core.config import get_settings
from app.core.database import AsyncSessionLocal
from app.core.encryption import get_encryption_keyring
from app.core.errors import install_exception_handlers
from app.core.observability import REQUEST_ID_HEADER, install_observability, metrics_response
from app.core.redis import close_redis, get_redis, ping_redis
from app.models.user import User
from app.services.attachments import cleanup_orphan_attachments
from app.services.presence import sweep_expired_presence
from app.services.push import drain_push_tasks, push_queue_worker
from app.websocket.manager import manager
from app.websocket.routes import participant_ids_for_user
from app.websocket.routes import router as websocket_router

logger = logging.getLogger(__name__)


def log_subscriber_failure(task: asyncio.Task) -> None:
    if task.cancelled():
        return
    exception = task.exception()
    if exception is not None:
        logger.error(
            "Redis Pub/Sub subscriber stopped unexpectedly",
            exc_info=(type(exception), exception, exception.__traceback__),
        )


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    settings.upload_dir.mkdir(parents=True, exist_ok=True)
    await ping_redis()
    redis = await get_redis()
    subscriber = asyncio.create_task(manager.redis_subscriber(redis))
    subscriber.add_done_callback(log_subscriber_failure)
    app.state.redis_subscriber_task = subscriber
    push_worker = asyncio.create_task(push_queue_worker())
    app.state.push_worker_task = push_worker
    sweeper = asyncio.create_task(presence_sweeper(redis))
    app.state.presence_sweeper_task = sweeper
    gc_task = asyncio.create_task(orphan_attachment_gc())
    app.state.attachment_gc_task = gc_task
    try:
        yield
    finally:
        subscriber.cancel()
        with suppress(asyncio.CancelledError):
            await subscriber
        push_worker.cancel()
        with suppress(asyncio.CancelledError):
            await push_worker
        sweeper.cancel()
        with suppress(asyncio.CancelledError):
            await sweeper
        gc_task.cancel()
        with suppress(asyncio.CancelledError):
            await gc_task
        await drain_push_tasks()
        app.state.redis_subscriber_task = None
        await close_redis()


async def presence_sweeper(redis) -> None:
    from datetime import UTC, datetime

    while True:
        await asyncio.sleep(30)
        try:
            expired = await sweep_expired_presence(redis)
            if not expired:
                continue
            now = datetime.now(UTC)
            peers: set[str] = set()
            async with AsyncSessionLocal() as db:
                for user_id in expired:
                    user = await db.get(User, user_id)
                    if user is not None:
                        user.last_seen_at = now
                await db.commit()
                for user_id in expired:
                    peers.update(await participant_ids_for_user(db, user_id))
            if peers:
                for user_id in expired:
                    await manager.broadcast_to_users(
                        redis,
                        list(peers),
                        "user:offline",
                        {"user_id": user_id, "last_seen_at": now.isoformat()},
                    )
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Presence sweep failed")


async def orphan_attachment_gc() -> None:
    while True:
        await asyncio.sleep(3600)
        try:
            removed = await cleanup_orphan_attachments()
            if removed:
                logger.info("Cleaned up %s orphaned attachments", removed)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Orphan attachment cleanup failed")


settings = get_settings()
get_encryption_keyring()
settings.upload_dir.mkdir(parents=True, exist_ok=True)
(settings.upload_dir / "avatars").mkdir(parents=True, exist_ok=True)
app = FastAPI(title=settings.app_name, version="1.2.1", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=[REQUEST_ID_HEADER],
)
install_observability(app)
install_exception_handlers(app)

app.include_router(auth.router)
app.include_router(users.router)
app.include_router(conversations.router)
app.include_router(messages.router)
app.include_router(search.router)
app.include_router(attachments.router)
app.include_router(devices.router)
app.include_router(websocket_router)

MAX_JSON_BODY_BYTES = 1_048_576
BODY_CAP_EXEMPT_PATHS = ("/attachments/upload", "/users/me/avatar")


@app.middleware("http")
async def limit_request_body(request: Request, call_next):
    if (
        request.method in {"POST", "PUT", "PATCH"}
        and not request.url.path.startswith(BODY_CAP_EXEMPT_PATHS)
    ):
        content_length = request.headers.get("content-length")
        if content_length and content_length.isdigit() and int(content_length) > MAX_JSON_BODY_BYTES:
            return JSONResponse(
                {"detail": "Request body too large"},
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            )
    return await call_next(request)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/health/ready")
async def readiness() -> JSONResponse:
    checks = {"database": False, "redis": False, "subscriber": False}
    try:
        async with AsyncSessionLocal() as db:
            await db.execute(text("SELECT 1"))
        checks["database"] = True
    except Exception:
        logger.exception("Database readiness check failed")
    try:
        await ping_redis()
        checks["redis"] = True
    except Exception:
        logger.exception("Redis readiness check failed")
    subscriber = getattr(app.state, "redis_subscriber_task", None)
    checks["subscriber"] = subscriber is not None and not subscriber.done()

    ready = all(checks.values())
    return JSONResponse(
        {"status": "ok" if ready else "not_ready", "checks": checks},
        status_code=status.HTTP_200_OK if ready else status.HTTP_503_SERVICE_UNAVAILABLE,
    )


@app.get("/metrics", include_in_schema=False)
async def metrics(request: Request):
    return metrics_response(
        request,
        enabled=settings.metrics_enabled,
        bearer_token=settings.metrics_bearer_token,
    )
