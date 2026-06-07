from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, UploadFile, status
from fastapi.responses import FileResponse

from app.api.deps import CurrentUser, DbSession
from app.schemas.attachment import AttachmentOut
from app.services.conversations import require_participant
from app.services.attachments import require_attachment_access, save_upload

router = APIRouter(prefix="/attachments", tags=["attachments"])


@router.post("/upload", response_model=AttachmentOut, status_code=status.HTTP_201_CREATED)
async def upload_attachment(
    current_user: CurrentUser,
    db: DbSession,
    file: UploadFile = File(...),
    conversation_id: str | None = Form(default=None),
) -> AttachmentOut:
    if conversation_id:
        await require_participant(db, conversation_id, current_user.id)
    attachment = await save_upload(db, current_user, file)
    return AttachmentOut.model_validate(attachment)


@router.get("/{attachment_id}", response_model=AttachmentOut)
async def get_attachment(attachment_id: str, current_user: CurrentUser, db: DbSession) -> AttachmentOut:
    attachment = await require_attachment_access(db, attachment_id, current_user.id)
    return AttachmentOut.model_validate(attachment)


@router.get("/{attachment_id}/download")
async def download_attachment(attachment_id: str, current_user: CurrentUser, db: DbSession) -> FileResponse:
    attachment = await require_attachment_access(db, attachment_id, current_user.id)
    path = Path(attachment.storage_path)
    if not path.exists():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "File missing from storage")
    return FileResponse(path, filename=attachment.original_filename, media_type=attachment.mime_type)
