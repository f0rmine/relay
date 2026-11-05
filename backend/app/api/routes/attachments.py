from typing import Annotated
from urllib.parse import quote

from fastapi import APIRouter, File, Form, HTTPException, Query, Request, UploadFile, status
from fastapi.responses import Response

from app.api.deps import CurrentUser, DbSession
from app.schemas.attachment import AttachmentOut
from app.services.attachments import read_attachment_bytes, require_attachment_access, save_upload
from app.services.conversations import require_participant

router = APIRouter(prefix="/attachments", tags=["attachments"])


def _is_inline_mime(mime_type: str) -> bool:
    return (
        mime_type.startswith(("image/", "video/", "audio/"))
        or mime_type in ("application/pdf", "text/plain")
    )


def _parse_range(range_header: str, total: int) -> tuple[int, int]:
    """Parse a single-range 'bytes=start-end' header. Returns (start, end_exclusive)."""
    if total <= 0:
        raise HTTPException(status.HTTP_416_RANGE_NOT_SATISFIABLE, "Empty content")
    spec = range_header.strip()
    if not spec.startswith("bytes="):
        raise HTTPException(status.HTTP_416_RANGE_NOT_SATISFIABLE, "Invalid range")
    spec = spec[len("bytes=") :]
    if "," in spec:
        raise HTTPException(
            status.HTTP_416_RANGE_NOT_SATISFIABLE, "Multiple ranges not supported"
        )
    parts = spec.split("-")
    if len(parts) != 2:
        raise HTTPException(status.HTTP_416_RANGE_NOT_SATISFIABLE, "Invalid range")
    start_str, end_str = parts
    if start_str == "" and end_str == "":
        raise HTTPException(status.HTTP_416_RANGE_NOT_SATISFIABLE, "Invalid range")
    if start_str == "":
        try:
            suffix = int(end_str)
        except ValueError:
            raise HTTPException(
                status.HTTP_416_RANGE_NOT_SATISFIABLE, "Invalid range"
            ) from None
        if suffix <= 0:
            raise HTTPException(status.HTTP_416_RANGE_NOT_SATISFIABLE, "Invalid range")
        start = max(0, total - suffix)
        end = total
    else:
        try:
            start = int(start_str)
            end = int(end_str) + 1 if end_str else total
        except ValueError:
            raise HTTPException(
                status.HTTP_416_RANGE_NOT_SATISFIABLE, "Invalid range"
            ) from None
        if start < 0 or end <= start or start >= total:
            raise HTTPException(status.HTTP_416_RANGE_NOT_SATISFIABLE, "Range out of bounds")
        end = min(end, total)
    return start, end


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
    request: Request,
    current_user: CurrentUser,
    db: DbSession,
    variant: str = Query(default="full", pattern="^(full|thumb)$"),
) -> Response:
    attachment = await require_attachment_access(db, attachment_id, current_user.id)
    content = await read_attachment_bytes(attachment, variant)
    use_thumb = variant == "thumb" and attachment.thumb_path is not None
    media_type = "image/jpeg" if use_thumb else attachment.mime_type
    disposition = "inline" if _is_inline_mime(media_type) else "attachment"
    headers: dict[str, str] = {
        "Content-Disposition": f"{disposition}; filename*=UTF-8''{quote(attachment.original_filename)}",
        "Accept-Ranges": "bytes",
        "Content-Length": str(len(content)),
        "Cache-Control": "private, max-age=3600",
    }
    range_header = request.headers.get("range")
    if range_header:
        start, end = _parse_range(range_header, len(content))
        body = content[start:end]
        headers["Content-Range"] = f"bytes {start}-{end - 1}/{len(content)}"
        headers["Content-Length"] = str(len(body))
        return Response(
            content=body,
            media_type=media_type,
            status_code=status.HTTP_206_PARTIAL_CONTENT,
            headers=headers,
        )
    return Response(content=content, media_type=media_type, headers=headers)
