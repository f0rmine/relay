import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api.routes import attachments, auth, conversations, devices, messages, users
from app.core.config import get_settings
from app.core.errors import install_exception_handlers
from app.core.redis import close_redis, get_redis, ping_redis
from app.websocket.manager import manager
from app.websocket.routes import router as websocket_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    settings.upload_dir.mkdir(parents=True, exist_ok=True)
    if settings.redis_required:
        await ping_redis()
    redis = await get_redis()
    subscriber = asyncio.create_task(manager.redis_subscriber(redis))
    yield
    subscriber.cancel()
    await close_redis()


settings = get_settings()
settings.upload_dir.mkdir(parents=True, exist_ok=True)
(settings.upload_dir / "avatars").mkdir(parents=True, exist_ok=True)
app = FastAPI(title=settings.app_name, version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
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
