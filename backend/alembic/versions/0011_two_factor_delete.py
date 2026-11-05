"""two-factor auth and account deletion

Revision ID: 0011_two_factor_delete
Revises: 0010_scheduled_mentions_previews
Create Date: 2026-11-05
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0011_two_factor_delete"
down_revision: str | None = "0010_scheduled_mentions_previews"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("users", sa.Column("totp_secret_ciphertext", sa.LargeBinary, nullable=True))
    op.add_column(
        "users",
        sa.Column(
            "totp_enabled",
            sa.Boolean,
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.add_column("users", sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True))
    op.create_table(
        "recovery_codes",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("code_hash", sa.String(length=255), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_recovery_codes_user_id", "recovery_codes", ["user_id"])


def downgrade() -> None:
    op.drop_table("recovery_codes")
    op.drop_column("users", "deleted_at")
    op.drop_column("users", "totp_enabled")
    op.drop_column("users", "totp_secret_ciphertext")
