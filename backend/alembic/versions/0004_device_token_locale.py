"""add device token locale

Revision ID: 0004_device_token_locale
Revises: 0003_content_encryption
Create Date: 2026-06-23
"""

from alembic import op
import sqlalchemy as sa


revision = "0004_device_token_locale"
down_revision = "0003_content_encryption"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "device_tokens",
        sa.Column("locale", sa.String(length=2), server_default="en", nullable=False),
    )


def downgrade() -> None:
    op.drop_column("device_tokens", "locale")
