"""blocking, disappearing messages, and invite links

Revision ID: 0012_block_disappear_invites
Revises: 0011_two_factor_delete
Create Date: 2026-11-05
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0012_block_disappear_invites"
down_revision: str | None = "0011_two_factor_delete"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "user_blocks",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("blocker_id", sa.String(length=36), nullable=False),
        sa.Column("blocked_id", sa.String(length=36), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(["blocker_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["blocked_id"], ["users.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("blocker_id", "blocked_id", name="uq_user_block"),
    )
    op.create_index("ix_user_blocks_blocker_id", "user_blocks", ["blocker_id"])
    op.create_index("ix_user_blocks_blocked_id", "user_blocks", ["blocked_id"])

    op.add_column(
        "conversations", sa.Column("disappearing_after_seconds", sa.Integer, nullable=True)
    )
    op.add_column(
        "conversations", sa.Column("invite_token", sa.String(length=64), nullable=True)
    )
    op.create_index(
        "uq_conversations_invite_token", "conversations", ["invite_token"], unique=True
    )

    op.add_column(
        "messages", sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.create_index("ix_messages_expires_at", "messages", ["expires_at"])


def downgrade() -> None:
    op.drop_index("ix_messages_expires_at", table_name="messages")
    op.drop_column("messages", "expires_at")
    op.drop_index("uq_conversations_invite_token", table_name="conversations")
    op.drop_column("conversations", "invite_token")
    op.drop_column("conversations", "disappearing_after_seconds")
    op.drop_index("ix_user_blocks_blocked_id", table_name="user_blocks")
    op.drop_index("ix_user_blocks_blocker_id", table_name="user_blocks")
    op.drop_table("user_blocks")
