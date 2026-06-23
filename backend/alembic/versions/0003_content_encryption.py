"""add encrypted message and attachment storage metadata

Revision ID: 0003_content_encryption
Revises: 0002_device_tokens
Create Date: 2026-06-23
"""

from alembic import op
import sqlalchemy as sa


revision = "0003_content_encryption"
down_revision = "0002_device_tokens"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("messages", sa.Column("text_ciphertext", sa.LargeBinary(), nullable=True))
    op.add_column("messages", sa.Column("text_nonce", sa.LargeBinary(), nullable=True))
    op.add_column("messages", sa.Column("text_key_id", sa.String(length=100), nullable=True))
    op.add_column("messages", sa.Column("encryption_version", sa.Integer(), nullable=True))
    op.add_column("attachments", sa.Column("encrypted_path", sa.String(length=700), nullable=True))
    op.add_column("attachments", sa.Column("encryption_nonce", sa.LargeBinary(), nullable=True))
    op.add_column(
        "attachments", sa.Column("encryption_key_id", sa.String(length=100), nullable=True)
    )
    op.add_column("attachments", sa.Column("encryption_version", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("attachments", "encryption_version")
    op.drop_column("attachments", "encryption_key_id")
    op.drop_column("attachments", "encryption_nonce")
    op.drop_column("attachments", "encrypted_path")
    op.drop_column("messages", "encryption_version")
    op.drop_column("messages", "text_key_id")
    op.drop_column("messages", "text_nonce")
    op.drop_column("messages", "text_ciphertext")
