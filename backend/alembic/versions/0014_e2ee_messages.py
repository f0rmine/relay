"""E2EE messages: per-device envelopes and e2ee flags

Revision ID: 0014_e2ee_messages
Revises: 0013_e2ee_key_directory
Create Date: 2026-11-16
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0014_e2ee_messages"
down_revision: str | None = "0013_e2ee_key_directory"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "conversations",
        sa.Column("e2ee", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column(
        "messages",
        sa.Column("e2ee", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column("messages", sa.Column("sender_device_id", sa.String(length=64), nullable=True))
    op.create_table(
        "message_envelopes",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("message_id", sa.String(length=36), nullable=False),
        sa.Column("recipient_user_id", sa.String(length=36), nullable=False),
        sa.Column("recipient_device_id", sa.String(length=64), nullable=False),
        sa.Column("ciphertext", sa.Text(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.ForeignKeyConstraint(["message_id"], ["messages.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["recipient_user_id"], ["users.id"], ondelete="CASCADE"),
        sa.UniqueConstraint(
            "message_id", "recipient_user_id", "recipient_device_id", name="uq_message_envelope"
        ),
    )
    op.create_index("ix_message_envelopes_message_id", "message_envelopes", ["message_id"])
    op.create_index(
        "ix_message_envelopes_recipient",
        "message_envelopes",
        ["recipient_user_id", "recipient_device_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_message_envelopes_recipient", table_name="message_envelopes")
    op.drop_index("ix_message_envelopes_message_id", table_name="message_envelopes")
    op.drop_table("message_envelopes")
    op.drop_column("messages", "sender_device_id")
    op.drop_column("messages", "e2ee")
    op.drop_column("conversations", "e2ee")
