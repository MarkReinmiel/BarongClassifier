"""Per-section onboarding tour progress JSON.

Revision ID: 20261107_0008
Revises: 20261106_0007
Create Date: 2026-11-07
"""

from alembic import op
import sqlalchemy as sa

revision = "20261107_0008"
down_revision = "20261106_0007"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "users",
        sa.Column("tour_progress", sa.Text(), nullable=True),
        schema="customer",
    )
    # Seed from legacy tour_completed so existing users are not re-toured.
    # Use exec_driver_sql so JSON ":true" is not treated as a SQLAlchemy bind.
    conn = op.get_bind()
    conn.exec_driver_sql(
        """
        update customer.users
        set tour_progress = case
          when coalesce(tour_completed, false) then
            '{"main":true,"textile":true,"history":true,"profile":true}'
          else
            '{"main":false,"textile":false,"history":false,"profile":false}'
          end
        where tour_progress is null
        """
    )


def downgrade():
    op.drop_column("users", "tour_progress", schema="customer")
