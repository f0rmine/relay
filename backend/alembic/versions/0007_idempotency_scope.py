"""scope message idempotency key to conversation

Revision ID: 0007_idempotency_scope
Revises: 0006_message_idempotency
Create Date: 2026-08-25
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0007_idempotency_scope"
down_revision: str | None = "0006_message_idempotency"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint("uq_messages_sender_client_message", "messages", type_="unique")
    op.create_unique_constraint(
        "uq_messages_sender_conversation_client_message",
        "messages",
        ["sender_id", "conversation_id", "client_message_id"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_messages_sender_conversation_client_message", "messages", type_="unique"
    )
    op.create_unique_constraint(
        "uq_messages_sender_client_message",
        "messages",
        ["sender_id", "client_message_id"],
    )
