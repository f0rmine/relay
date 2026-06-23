from datetime import datetime
from uuid import uuid4

from sqlalchemy import DateTime, ForeignKey, Integer, LargeBinary, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class Attachment(Base):
    __tablename__ = "attachments"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    message_id: Mapped[str | None] = mapped_column(
        ForeignKey("messages.id", ondelete="SET NULL"), index=True, nullable=True
    )
    uploader_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    stored_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(120), nullable=False)
    file_size: Mapped[int] = mapped_column(Integer, nullable=False)
    storage_path: Mapped[str] = mapped_column(String(700), nullable=False)
    encrypted_path: Mapped[str | None] = mapped_column(String(700), nullable=True)
    public_url: Mapped[str] = mapped_column(String(700), nullable=False)
    encryption_nonce: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    encryption_key_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    encryption_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    message = relationship("Message", back_populates="attachments")
    uploader = relationship("User")
