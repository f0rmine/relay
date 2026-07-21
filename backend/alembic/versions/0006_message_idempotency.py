"""add client message idempotency key

Revision ID: 0006_message_idempotency
Revises: 0005_token_jti
Create Date: 2026-07-22
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006_message_idempotency"
down_revision: str | None = "0005_token_jti"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "messages",
        sa.Column("client_message_id", sa.String(length=100), nullable=True),
    )
    op.create_unique_constraint(
        "uq_messages_sender_client_message",
        "messages",
        ["sender_id", "client_message_id"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_messages_sender_client_message",
        "messages",
        type_="unique",
    )
    op.drop_column("messages", "client_message_id")
