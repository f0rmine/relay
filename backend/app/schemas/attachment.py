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
    created_at: datetime
