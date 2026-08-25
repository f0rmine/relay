from typing import Annotated
from urllib.parse import quote

from fastapi import APIRouter, File, Form, Query, UploadFile, status
from fastapi.responses import Response

from app.api.deps import CurrentUser, DbSession
from app.schemas.attachment import AttachmentOut
from app.services.attachments import read_attachment_bytes, require_attachment_access, save_upload
from app.services.conversations import require_participant

router = APIRouter(prefix="/attachments", tags=["attachments"])


@router.post("/upload", response_model=AttachmentOut, status_code=status.HTTP_201_CREATED)
async def upload_attachment(
    current_user: CurrentUser,
    db: DbSession,
    file: Annotated[UploadFile, File(...)],
    conversation_id: Annotated[str | None, Form()] = None,
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
async def download_attachment(
    attachment_id: str,
    current_user: CurrentUser,
    db: DbSession,
    variant: str = Query(default="full", pattern="^(full|thumb)$"),
) -> Response:
    attachment = await require_attachment_access(db, attachment_id, current_user.id)
    content = await read_attachment_bytes(attachment, variant)
    media_type = "image/jpeg" if variant == "thumb" else attachment.mime_type
    return Response(
        content=content,
        media_type=media_type,
        headers={
            "Content-Disposition": (
                f"attachment; filename*=UTF-8''{quote(attachment.original_filename)}"
            )
        },
    )
