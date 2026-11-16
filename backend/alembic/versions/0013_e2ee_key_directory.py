"""E2EE key directory: identities, signed devices, one-time prekeys

Replaces the unused, unauthenticated user_devices groundwork table.

Revision ID: 0013_e2ee_key_directory
Revises: 0012_block_disappear_invites
Create Date: 2026-11-16
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0013_e2ee_key_directory"
down_revision: str | None = "0012_block_disappear_invites"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _timestamp(name: str) -> sa.Column:
    return sa.Column(name, sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now())


def upgrade() -> None:
    op.create_table(
        "e2ee_identities",
        sa.Column("user_id", sa.String(length=36), primary_key=True),
        sa.Column("identity_key", sa.String(length=64), nullable=False),
        _timestamp("created_at"),
        _timestamp("updated_at"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
    )

    op.create_table(
        "e2ee_devices",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("device_id", sa.String(length=64), nullable=False),
        sa.Column("label", sa.String(length=120), nullable=True),
        sa.Column("signing_key", sa.String(length=64), nullable=False),
        sa.Column("agreement_key", sa.String(length=64), nullable=False),
        sa.Column("identity_signature", sa.String(length=128), nullable=False),
        sa.Column("signed_prekey_id", sa.Integer(), nullable=False),
        sa.Column("signed_prekey", sa.String(length=64), nullable=False),
        sa.Column("signed_prekey_signature", sa.String(length=128), nullable=False),
        sa.Column("pq_prekey_id", sa.Integer(), nullable=False),
        sa.Column("pq_prekey", sa.Text(), nullable=False),
        sa.Column("pq_prekey_signature", sa.String(length=128), nullable=False),
        _timestamp("created_at"),
        _timestamp("updated_at"),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("user_id", "device_id", name="uq_e2ee_device"),
    )
    op.create_index("ix_e2ee_devices_user_id", "e2ee_devices", ["user_id"])

    op.create_table(
        "e2ee_one_time_prekeys",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("device_pk", sa.String(length=36), nullable=False),
        sa.Column("kind", sa.String(length=8), nullable=False),
        sa.Column("key_id", sa.Integer(), nullable=False),
        sa.Column("public_key", sa.Text(), nullable=False),
        sa.Column("signature", sa.String(length=128), nullable=True),
        _timestamp("created_at"),
        sa.ForeignKeyConstraint(["device_pk"], ["e2ee_devices.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("device_pk", "kind", "key_id", name="uq_e2ee_otpk"),
    )
    op.create_index(
        "ix_e2ee_otpk_claim", "e2ee_one_time_prekeys", ["device_pk", "kind", "key_id"]
    )

    op.drop_index("ix_user_devices_user_id", table_name="user_devices")
    op.drop_table("user_devices")


def downgrade() -> None:
    op.create_table(
        "user_devices",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("public_key", sa.String(length=200), nullable=False),
        sa.Column("device_label", sa.String(length=120), nullable=True),
        _timestamp("added_at"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("user_id", "public_key", name="uq_user_device_public_key"),
    )
    op.create_index("ix_user_devices_user_id", "user_devices", ["user_id"])

    op.drop_index("ix_e2ee_otpk_claim", table_name="e2ee_one_time_prekeys")
    op.drop_table("e2ee_one_time_prekeys")
    op.drop_index("ix_e2ee_devices_user_id", table_name="e2ee_devices")
    op.drop_table("e2ee_devices")
    op.drop_table("e2ee_identities")
