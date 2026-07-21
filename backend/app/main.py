import asyncio
import logging
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text

from app.api.routes import attachments, auth, conversations, devices, messages, users
from app.core.config import get_settings
from app.core.database import AsyncSessionLocal
from app.core.encryption import get_encryption_keyring
from app.core.errors import install_exception_handlers
from app.core.observability import REQUEST_ID_HEADER, install_observability, metrics_response
from app.core.redis import close_redis, get_redis, ping_redis
from app.services.push import drain_push_tasks
from app.websocket.manager import manager
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
    try:
        yield
    finally:
        subscriber.cancel()
        with suppress(asyncio.CancelledError):
            await subscriber
        await drain_push_tasks()
        app.state.redis_subscriber_task = None
        await close_redis()


settings = get_settings()
get_encryption_keyring()
settings.upload_dir.mkdir(parents=True, exist_ok=True)
(settings.upload_dir / "avatars").mkdir(parents=True, exist_ok=True)
app = FastAPI(title=settings.app_name, version="1.2.0", lifespan=lifespan)

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
app.include_router(attachments.router)
app.include_router(devices.router)
app.include_router(websocket_router)

app.mount("/uploads/avatars", StaticFiles(directory=settings.upload_dir / "avatars"), name="avatars")


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
