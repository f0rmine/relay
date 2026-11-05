"""scheduled messages, mentions, link previews, export jobs

Revision ID: 0010_scheduled_mentions_previews
Revises: 0009_thumb_nonce
Create Date: 2026-11-05
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0010_scheduled_mentions_previews"
down_revision: str | None = "0009_thumb_nonce"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("messages", sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index("ix_messages_scheduled_at", "messages", ["scheduled_at"])
    op.add_column(
        "messages", sa.Column("scheduled_notified_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.create_index("ix_messages_scheduled_notified_at", "messages", ["scheduled_notified_at"])
    op.add_column("messages", sa.Column("mentions", sa.Text(), nullable=True))
    op.create_table(
        "link_previews",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("url", sa.String(length=2000), nullable=False),
        sa.Column("title", sa.String(length=500), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("image_url", sa.String(length=2000), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint("url", name="uq_link_previews_url"),
    )
    op.create_table(
        "export_jobs",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("conversation_id", sa.String(length=36), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="pending"),
        sa.Column("file_path", sa.String(length=700), nullable=True),
        sa.Column("error", sa.String(length=500), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["conversation_id"], ["conversations.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_export_jobs_user_id", "export_jobs", ["user_id"])


def downgrade() -> None:
    op.drop_table("export_jobs")
    op.drop_table("link_previews")
    op.drop_column("messages", "mentions")
    op.drop_index("ix_messages_scheduled_notified_at", table_name="messages")
    op.drop_column("messages", "scheduled_notified_at")
    op.drop_index("ix_messages_scheduled_at", table_name="messages")
    op.drop_column("messages", "scheduled_at")
