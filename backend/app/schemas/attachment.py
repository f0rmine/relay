from datetime import datetime

from app.schemas.common import OrmModel


class AttachmentOut(OrmModel):
    id: str
    message_id: str | None
    uploader_id: str
    original_filename: str
    mime_type: str
    file_size: int
    public_url: str
    thumb_w: int | None = None
    thumb_h: int | None = None
    thumb_size: int | None = None
    created_at: datetime
