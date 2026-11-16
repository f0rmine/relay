"""End-to-end encryption key directory (Phase 1).

The server stores only public keys and signatures. It verifies signatures on
upload so malformed records never enter the directory, but clients must verify
them again: the directory is untrusted by design (see docs/e2ee-roadmap.md).
"""

from datetime import datetime
from uuid import uuid4

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class E2eeIdentity(Base):
    __tablename__ = "e2ee_identities"

    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    identity_key: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class E2eeDevice(Base):
    __tablename__ = "e2ee_devices"
    __table_args__ = (UniqueConstraint("user_id", "device_id", name="uq_e2ee_device"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    device_id: Mapped[str] = mapped_column(String(64), nullable=False)
    label: Mapped[str | None] = mapped_column(String(120), nullable=True)
    signing_key: Mapped[str] = mapped_column(String(64), nullable=False)
    agreement_key: Mapped[str] = mapped_column(String(64), nullable=False)
    identity_signature: Mapped[str] = mapped_column(String(128), nullable=False)
    signed_prekey_id: Mapped[int] = mapped_column(Integer, nullable=False)
    signed_prekey: Mapped[str] = mapped_column(String(64), nullable=False)
    signed_prekey_signature: Mapped[str] = mapped_column(String(128), nullable=False)
    pq_prekey_id: Mapped[int] = mapped_column(Integer, nullable=False)
    pq_prekey: Mapped[str] = mapped_column(Text, nullable=False)
    pq_prekey_signature: Mapped[str] = mapped_column(String(128), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class E2eeOneTimePrekey(Base):
    """A one-time prekey; deleted (not marked) when claimed."""

    __tablename__ = "e2ee_one_time_prekeys"
    __table_args__ = (
        UniqueConstraint("device_pk", "kind", "key_id", name="uq_e2ee_otpk"),
        Index("ix_e2ee_otpk_claim", "device_pk", "kind", "key_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    device_pk: Mapped[str] = mapped_column(
        ForeignKey("e2ee_devices.id", ondelete="CASCADE"), nullable=False
    )
    # "ec" = X25519 (unsigned, as in X3DH); "kem" = ML-KEM-768 (signed by the device key).
    kind: Mapped[str] = mapped_column(String(8), nullable=False)
    key_id: Mapped[int] = mapped_column(Integer, nullable=False)
    public_key: Mapped[str] = mapped_column(Text, nullable=False)
    signature: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class MessageEnvelope(Base):
    """One device's ciphertext for an E2EE message. Opaque to the server."""

    __tablename__ = "message_envelopes"
    __table_args__ = (
        UniqueConstraint(
            "message_id", "recipient_user_id", "recipient_device_id", name="uq_message_envelope"
        ),
        Index("ix_message_envelopes_recipient", "recipient_user_id", "recipient_device_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    message_id: Mapped[str] = mapped_column(
        ForeignKey("messages.id", ondelete="CASCADE"), index=True, nullable=False
    )
    recipient_user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    recipient_device_id: Mapped[str] = mapped_column(String(64), nullable=False)
    ciphertext: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
