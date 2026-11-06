"""Add tour_completed flag for first-login onboarding tour.

Revision ID: 20261106_0007
Revises: 20261020_0006
Create Date: 2026-11-06
"""

from alembic import op
import sqlalchemy as sa

revision = "20261106_0007"
down_revision = "20261020_0006"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "users",
        sa.Column(
            "tour_completed",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        schema="customer",
    )
    # Existing members already finished setup — do not force the tour on them.
    op.execute(
        """
        update customer.users
        set tour_completed = true
        where nickname_completed = true
        """
    )


def downgrade():
    op.drop_column("users", "tour_completed", schema="customer")
