"""Expose customer portal tables as public views for Table Editor.

Revision ID: 20261020_0002
Revises: 20261020_0001
Create Date: 2026-10-20

public.users already exists for Supabase Auth / Frontend.
Flask Customer auth lives in schema customer.*. These views make that
data visible in the Supabase Table Editor without colliding with public.users.
"""

from alembic import op

revision = "20261020_0002"
down_revision = "20261020_0001"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        """
        create or replace view public.customer_portal_users as
        select
          id,
          email,
          email_verified,
          nickname,
          nickname_completed,
          is_active,
          created_at,
          updated_at,
          last_login_at
        from customer.users;

        create or replace view public.customer_portal_email_verifications as
        select
          id,
          user_id,
          purpose,
          expires_at,
          resend_available_at,
          attempts,
          locked_until,
          consumed_at,
          created_at
        from customer.email_verifications;

        create or replace view public.customer_portal_trusted_devices as
        select
          id,
          user_id,
          label,
          created_at,
          last_used_at,
          expires_at,
          revoked_at
        from customer.trusted_devices;

        create or replace view public.customer_portal_classifications as
        select
          id,
          user_id,
          predicted_label,
          confidence,
          image_name,
          image_path,
          created_at
        from customer.classifications;
        """
    )
    # Never expose password_hash or token_hash / code_hash through public views.
    op.execute("comment on view public.customer_portal_users is 'Flask Customer portal accounts (schema customer.users). Not the same as public.users (Supabase Auth mirror).'")


def downgrade():
    op.execute("drop view if exists public.customer_portal_classifications")
    op.execute("drop view if exists public.customer_portal_trusted_devices")
    op.execute("drop view if exists public.customer_portal_email_verifications")
    op.execute("drop view if exists public.customer_portal_users")
