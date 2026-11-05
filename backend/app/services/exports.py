import asyncio
import json
import logging
import zipfile
from contextlib import suppress
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.core.config import get_settings
from app.core.database import AsyncSessionLocal
from app.models.export_job import ExportJob
from app.models.message import Message
from app.models.user import User
from app.services.attachments import read_attachment_bytes
from app.services.conversations import require_participant
from app.services.messages import parse_mentions, plaintext_message_text

logger = logging.getLogger(__name__)


def exports_dir() -> Path:
    settings = get_settings()
    path = settings.upload_dir / "exports"
    path.mkdir(parents=True, exist_ok=True)
    return path


async def create_export_job(db, user: User, conversation_id: str) -> ExportJob:
    await require_participant(db, conversation_id, user.id)
    job = ExportJob(
        id=str(uuid4()),
        user_id=user.id,
        conversation_id=conversation_id,
        status="pending",
    )
    db.add(job)
    await db.commit()
    await db.refresh(job)
    return job


def _iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.isoformat()


async def build_export_zip(db, job: ExportJob) -> Path:
    messages = list(
        (
            await db.scalars(
                select(Message)
                .options(selectinload(Message.attachments))
                .where(
                    Message.conversation_id == job.conversation_id,
                    Message.deleted_at.is_(None),
                )
                .order_by(Message.created_at, Message.id)
            )
        ).all()
    )
    records: list[dict] = []
    buffers: list[tuple[str, bytes]] = []
    for message in messages:
        try:
            text = plaintext_message_text(message)
        except Exception:  # noqa: BLE001
            text = None
        attachments_meta: list[dict] = []
        for attachment in message.attachments:
            safe_name = Path(attachment.original_filename).name or "file"
            arcname = f"media/{attachment.id}_{safe_name}"
            try:
                data = await read_attachment_bytes(attachment)
                buffers.append((arcname, data))
            except Exception:
                logger.exception("Export skipped unreadable attachment %s", attachment.id)
                continue
            attachments_meta.append(
                {
                    "id": attachment.id,
                    "filename": safe_name,
                    "mime_type": attachment.mime_type,
                    "file_size": attachment.file_size,
                    "path": arcname,
                }
            )
        records.append(
            {
                "id": message.id,
                "conversation_id": message.conversation_id,
                "sender_id": message.sender_id,
                "text": text,
                "created_at": _iso(message.created_at),
                "scheduled_at": _iso(message.scheduled_at),
                "mentions": parse_mentions(message),
                "attachments": attachments_meta,
            }
        )
    export_path = exports_dir() / f"{job.id}.zip"
    export_path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(records, ensure_ascii=False, indent=2).encode("utf-8")
    # Write zip to disk.
    with zipfile.ZipFile(export_path, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("messages.json", payload)
        for arcname, data in buffers:
            archive.writestr(arcname, data)
    return export_path


async def _process_job(job_id: str, db=None) -> None:
    if db is None:
        async with AsyncSessionLocal() as session:
            await _process_job(job_id, session)
        return
    job = await db.get(ExportJob, job_id)
    if job is None:
        return
    if job.status != "pending":
        return
    job.status = "processing"
    await db.commit()
    try:
        # Re-check participant still has access at build time.
        await require_participant(db, job.conversation_id, job.user_id)
        path = await build_export_zip(db, job)
        job.file_path = str(path)
        job.status = "done"
        job.finished_at = datetime.now(UTC)
        job.error = None
    except Exception as exc:  # noqa: BLE001
        job.status = "error"
        job.error = str(exc)[:500]
        job.finished_at = datetime.now(UTC)
    await db.commit()


async def process_pending_jobs(limit: int = 5, db=None) -> int:
    if db is None:
        async with AsyncSessionLocal() as session:
            return await process_pending_jobs(limit, session)
    jobs = list(
        (
            await db.scalars(
                select(ExportJob)
                .where(ExportJob.status == "pending")
                .order_by(ExportJob.created_at)
                .limit(limit)
            )
        ).all()
    )
    ids = [job.id for job in jobs]
    for job_id in ids:
        await _process_job(job_id, db)
    return len(ids)


async def process_export_job(job_id: str, db=None) -> ExportJob | None:
    if db is None:
        async with AsyncSessionLocal() as session:
            await _process_job(job_id, session)
            return await session.get(ExportJob, job_id)
    await _process_job(job_id, db)
    return await db.get(ExportJob, job_id)


async def export_worker() -> None:
    while True:
        await asyncio.sleep(10)
        try:
            await process_pending_jobs()
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Export worker cycle failed")


async def cleanup_old_exports(db=None) -> int:
    if db is None:
        async with AsyncSessionLocal() as session:
            return await cleanup_old_exports(session)
    cutoff = datetime.now(UTC) - timedelta(hours=24)
    jobs = list(
        (
            await db.scalars(
                select(ExportJob).where(
                    ExportJob.finished_at.is_not(None),
                    ExportJob.finished_at < cutoff,
                )
            )
        ).all()
    )
    for job in jobs:
        if job.file_path:
            with suppress(OSError):
                Path(job.file_path).unlink(missing_ok=True)
        await db.delete(job)
    if jobs:
        await db.commit()
    return len(jobs)


async def get_export_job_for_user(db, job_id: str, user_id: str) -> ExportJob:
    from fastapi import HTTPException, status

    job = await db.get(ExportJob, job_id)
    if job is None or job.user_id != user_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Export not found")
    return job
