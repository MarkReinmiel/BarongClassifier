"""customer schema auth tables

Revision ID: 20261020_0001
Revises:
Create Date: 2026-10-20
"""

from alembic import op
import sqlalchemy as sa

revision = "20261020_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.execute("CREATE SCHEMA IF NOT EXISTS customer")
    op.create_table(
        "users",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("email_verified", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("nickname", sa.String(length=40)),
        sa.Column("nickname_completed", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_login_at", sa.DateTime(timezone=True)),
        schema="customer",
    )
    op.create_index("ix_customer_users_email", "users", ["email"], unique=True, schema="customer")

    op.create_table(
        "email_verifications",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("user_id", sa.String(length=36), sa.ForeignKey("customer.users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("purpose", sa.String(length=32), nullable=False),
        sa.Column("code_hash", sa.String(length=128), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("resend_available_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("locked_until", sa.DateTime(timezone=True)),
        sa.Column("consumed_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        schema="customer",
    )
    op.create_index(
        "ix_customer_email_verifications_user_id",
        "email_verifications",
        ["user_id"],
        schema="customer",
    )

    op.create_table(
        "trusted_devices",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("user_id", sa.String(length=36), sa.ForeignKey("customer.users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("token_hash", sa.String(length=128), nullable=False, unique=True),
        sa.Column("label", sa.String(length=120)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
        schema="customer",
    )
    op.create_index(
        "ix_customer_trusted_devices_user_id",
        "trusted_devices",
        ["user_id"],
        schema="customer",
    )

    op.create_table(
        "classifications",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("user_id", sa.String(length=36), sa.ForeignKey("customer.users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("predicted_label", sa.String(length=64), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("image_name", sa.String(length=255)),
        sa.Column("image_path", sa.String(length=512)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        schema="customer",
    )
    op.create_index(
        "ix_customer_classifications_user_id",
        "classifications",
        ["user_id"],
        schema="customer",
    )


def downgrade():
    op.drop_table("classifications", schema="customer")
    op.drop_table("trusted_devices", schema="customer")
    op.drop_table("email_verifications", schema="customer")
    op.drop_table("users", schema="customer")
