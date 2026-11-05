"""store separate thumbnail encryption nonce

Revision ID: 0009_thumb_nonce
Revises: 0008_feature_bundle
Create Date: 2026-08-26

Thumbnails were encrypted with a fresh nonce that was never persisted,
so thumb downloads could not be decrypted. Add dedicated thumb columns.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0009_thumb_nonce"
down_revision: str | None = "0008_feature_bundle"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("attachments", sa.Column("thumb_nonce", sa.LargeBinary(), nullable=True))
    op.add_column("attachments", sa.Column("thumb_key_id", sa.String(length=100), nullable=True))
    op.add_column("attachments", sa.Column("thumb_version", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("attachments", "thumb_version")
    op.drop_column("attachments", "thumb_key_id")
    op.drop_column("attachments", "thumb_nonce")
