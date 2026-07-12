"""add indexed token identifiers

Revision ID: 0005_token_jti
Revises: 0004_device_token_locale
Create Date: 2026-07-11
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005_token_jti"
down_revision: str | None = "0004_device_token_locale"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("refresh_tokens", sa.Column("jti", sa.String(length=36), nullable=True))
    op.create_index("ix_refresh_tokens_jti", "refresh_tokens", ["jti"], unique=True)
    op.add_column("password_reset_tokens", sa.Column("jti", sa.String(length=36), nullable=True))
    op.create_index(
        "ix_password_reset_tokens_jti", "password_reset_tokens", ["jti"], unique=True
    )


def downgrade() -> None:
    op.drop_index("ix_password_reset_tokens_jti", table_name="password_reset_tokens")
    op.drop_column("password_reset_tokens", "jti")
    op.drop_index("ix_refresh_tokens_jti", table_name="refresh_tokens")
    op.drop_column("refresh_tokens", "jti")
