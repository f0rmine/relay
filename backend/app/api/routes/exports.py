import logging

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from app.api.deps import CurrentUser, DbSession
from app.models.export_job import ExportJob
from app.services.exports import create_export_job, get_export_job_for_user, process_pending_jobs

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/exports", tags=["exports"])


class ExportCreate(BaseModel):
    conversation_id: str = Field(min_length=1, max_length=36)


class ExportOut(BaseModel):
    id: str
    conversation_id: str
    status: str
    file_path: str | None = None
    error: str | None = None


def _serialize(job: ExportJob) -> ExportOut:
    return ExportOut(
        id=job.id,
        conversation_id=job.conversation_id,
        status=job.status,
        file_path=job.file_path,
        error=job.error,
    )


@router.post("", response_model=ExportOut, status_code=status.HTTP_201_CREATED)
async def create_export(
    payload: ExportCreate,
    current_user: CurrentUser,
    db: DbSession,
) -> ExportOut:
    job = await create_export_job(db, current_user, payload.conversation_id)
    try:
        await process_pending_jobs(limit=1, db=db)
    except Exception:
        logger.exception("Immediate export processing failed")
    refreshed = await db.get(ExportJob, job.id)
    assert refreshed is not None
    return _serialize(refreshed)


@router.get("/{job_id}", response_model=ExportOut)
async def get_export(
    job_id: str,
    current_user: CurrentUser,
    db: DbSession,
) -> ExportOut:
    job = await get_export_job_for_user(db, job_id, current_user.id)
    return _serialize(job)


@router.get("/{job_id}/download")
async def download_export(
    job_id: str,
    current_user: CurrentUser,
    db: DbSession,
) -> FileResponse:
    job = await get_export_job_for_user(db, job_id, current_user.id)
    if job.status != "done" or not job.file_path:
        raise HTTPException(status.HTTP_409_CONFLICT, "Export is not ready")
    from pathlib import Path

    path = Path(job.file_path)
    if not path.exists():
        raise HTTPException(status.HTTP_410_GONE, "Export file expired")
    return FileResponse(path, media_type="application/zip", filename=f"export-{job.id}.zip")
