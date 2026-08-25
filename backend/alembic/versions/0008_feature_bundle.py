"""feature bundle: groups, replies, reactions, pins, thumbnails, device keys

Revision ID: 0008_feature_bundle
Revises: 0007_idempotency_scope
Create Date: 2026-08-25
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0008_feature_bundle"
down_revision: str | None = "0007_idempotency_scope"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("conversations", sa.Column("title", sa.String(length=120), nullable=True))
    op.add_column("conversations", sa.Column("avatar_url", sa.String(length=700), nullable=True))
    op.add_column(
        "conversations",
        sa.Column(
            "pinned_message_id",
            sa.String(length=36),
            nullable=True,
        ),
    )
    op.create_foreign_key(
        "fk_conversations_pinned_message",
        "conversations",
        "messages",
        ["pinned_message_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.add_column(
        "conversation_participants",
        sa.Column(
            "is_admin", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
    )
    op.add_column(
        "messages",
        sa.Column("reply_to_id", sa.String(length=36), nullable=True),
    )
    op.create_foreign_key(
        "fk_messages_reply_to", "messages", "messages", ["reply_to_id"], ["id"], ondelete="SET NULL"
    )
    op.create_table(
        "message_reactions",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("message_id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("emoji", sa.String(length=16), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(["message_id"], ["messages.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("message_id", "user_id", name="uq_message_reaction_user"),
    )
    op.create_index("ix_message_reactions_message_id", "message_reactions", ["message_id"])
    op.create_index("ix_message_reactions_user_id", "message_reactions", ["user_id"])
    for column in ("thumb_path", "thumb_size", "thumb_w", "thumb_h"):
        op.add_column("attachments", sa.Column(column, sa.String(length=700) if column == "thumb_path" else sa.Integer(), nullable=True))
    op.create_table(
        "user_devices",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("public_key", sa.String(length=200), nullable=False),
        sa.Column("device_label", sa.String(length=120), nullable=True),
        sa.Column(
            "added_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("user_id", "public_key", name="uq_user_device_public_key"),
    )
    op.create_index("ix_user_devices_user_id", "user_devices", ["user_id"])


def downgrade() -> None:
    op.drop_table("user_devices")
    for column in ("thumb_path", "thumb_size", "thumb_w", "thumb_h"):
        op.drop_column("attachments", column)
    op.drop_index("ix_message_reactions_user_id", table_name="message_reactions")
    op.drop_index("ix_message_reactions_message_id", table_name="message_reactions")
    op.drop_table("message_reactions")
    op.drop_constraint("fk_messages_reply_to", "messages", type_="foreignkey")
    op.drop_column("messages", "reply_to_id")
    op.drop_column("conversation_participants", "is_admin")
    op.drop_constraint("fk_conversations_pinned_message", "conversations", type_="foreignkey")
    op.drop_column("conversations", "pinned_message_id")
    op.drop_column("conversations", "avatar_url")
    op.drop_column("conversations", "title")
