"""Defer incomplete signups to customer.pending_signups.

Revision ID: 20261107_0009
Revises: 20261107_0008
Create Date: 2026-11-07
"""

from alembic import op
import sqlalchemy as sa

revision = "20261107_0009"
down_revision = "20261107_0008"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "pending_signups",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("code_hash", sa.String(length=128), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="pending"),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("resend_available_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("locked_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        schema="customer",
    )
    op.create_index(
        "ix_customer_pending_signups_email",
        "pending_signups",
        ["email"],
        unique=True,
        schema="customer",
    )


def downgrade():
    op.drop_index(
        "ix_customer_pending_signups_email",
        table_name="pending_signups",
        schema="customer",
    )
    op.drop_table("pending_signups", schema="customer")
