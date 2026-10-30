"""Drop portal views; add role/status on customer owner tables.

Revision ID: 20261020_0003
Revises: 20261020_0002
Create Date: 2026-10-20

customer_portal_* views duplicated the real tables. Keep one set of tables
(customer.users / email_verifications / trusted_devices / classifications)
and align them with owner-style role + status columns (like public.users).
"""

from alembic import op
import sqlalchemy as sa

revision = "20261020_0003"
down_revision = "20261020_0002"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("drop view if exists public.customer_portal_classifications")
    op.execute("drop view if exists public.customer_portal_trusted_devices")
    op.execute("drop view if exists public.customer_portal_email_verifications")
    op.execute("drop view if exists public.customer_portal_users")

    op.add_column(
        "users",
        sa.Column("full_name", sa.String(length=120), nullable=False, server_default=""),
        schema="customer",
    )
    op.add_column(
        "users",
        sa.Column("role", sa.String(length=32), nullable=False, server_default="customer"),
        schema="customer",
    )
    op.add_column(
        "users",
        sa.Column("status", sa.String(length=32), nullable=False, server_default="active"),
        schema="customer",
    )
    op.execute(
        """
        update customer.users
        set full_name = coalesce(nullif(trim(nickname), ''), ''),
            role = 'customer',
            status = case
              when is_active = false then 'disabled'
              when email_verified = false then 'pending_verification'
              else 'active'
            end
        """
    )

    op.add_column(
        "email_verifications",
        sa.Column("role", sa.String(length=32), nullable=False, server_default="customer"),
        schema="customer",
    )
    op.add_column(
        "email_verifications",
        sa.Column("status", sa.String(length=32), nullable=False, server_default="pending"),
        schema="customer",
    )
    op.execute(
        """
        update customer.email_verifications
        set role = coalesce(
              (select u.role from customer.users u where u.id = user_id),
              'customer'
            ),
            status = case
              when consumed_at is not null then 'consumed'
              when locked_until is not null and locked_until > now() then 'locked'
              when expires_at <= now() then 'expired'
              else 'pending'
            end
        """
    )

    op.add_column(
        "trusted_devices",
        sa.Column("role", sa.String(length=32), nullable=False, server_default="customer"),
        schema="customer",
    )
    op.add_column(
        "trusted_devices",
        sa.Column("status", sa.String(length=32), nullable=False, server_default="active"),
        schema="customer",
    )
    op.execute(
        """
        update customer.trusted_devices
        set role = coalesce(
              (select u.role from customer.users u where u.id = user_id),
              'customer'
            ),
            status = case
              when revoked_at is not null then 'revoked'
              when expires_at <= now() then 'expired'
              else 'active'
            end
        """
    )

    op.add_column(
        "classifications",
        sa.Column("role", sa.String(length=32), nullable=False, server_default="customer"),
        schema="customer",
    )
    op.add_column(
        "classifications",
        sa.Column("status", sa.String(length=32), nullable=False, server_default="completed"),
        schema="customer",
    )
    op.execute(
        """
        update customer.classifications
        set role = coalesce(
              (select u.role from customer.users u where u.id = user_id),
              'customer'
            ),
            status = 'completed'
        """
    )

    # Public Table Editor: same table names as owner where free (not users/classifications).
    op.execute(
        """
        create or replace view public.email_verifications as
        select
          id,
          user_id,
          purpose,
          expires_at,
          resend_available_at,
          attempts,
          locked_until,
          consumed_at,
          created_at,
          role,
          status
        from customer.email_verifications;

        create or replace view public.trusted_devices as
        select
          id,
          user_id,
          label,
          created_at,
          last_used_at,
          expires_at,
          revoked_at,
          role,
          status
        from customer.trusted_devices;

        -- users + portal accounts as one directory (public.users stays Auth-owned).
        create or replace view public.users_directory as
        select
          id::text as id,
          email,
          full_name,
          role::text as role,
          case when is_active then 'active' else 'disabled' end as status,
          is_active,
          email_verified,
          created_at,
          updated_at,
          last_sign_in_at as last_login_at,
          'auth'::text as source
        from public.users
        union all
        select
          id,
          email,
          full_name,
          role,
          status,
          is_active,
          email_verified,
          created_at,
          updated_at,
          last_login_at,
          'customer'::text as source
        from customer.users;

        create or replace view public.portal_classifications as
        select
          id,
          user_id,
          predicted_label,
          confidence,
          image_name,
          image_path,
          created_at,
          role,
          status
        from customer.classifications;
        """
    )
    op.execute(
        "comment on view public.users_directory is "
        "'Unified Auth public.users + Flask customer.users (role/status).'"
    )


def downgrade():
    op.execute("drop view if exists public.portal_classifications")
    op.execute("drop view if exists public.users_directory")
    op.execute("drop view if exists public.trusted_devices")
    op.execute("drop view if exists public.email_verifications")

    op.drop_column("classifications", "status", schema="customer")
    op.drop_column("classifications", "role", schema="customer")
    op.drop_column("trusted_devices", "status", schema="customer")
    op.drop_column("trusted_devices", "role", schema="customer")
    op.drop_column("email_verifications", "status", schema="customer")
    op.drop_column("email_verifications", "role", schema="customer")
    op.drop_column("users", "status", schema="customer")
    op.drop_column("users", "role", schema="customer")
    op.drop_column("users", "full_name", schema="customer")

    op.execute(
        """
        create or replace view public.customer_portal_users as
        select id, email, email_verified, nickname, nickname_completed, is_active,
               created_at, updated_at, last_login_at
        from customer.users;

        create or replace view public.customer_portal_email_verifications as
        select id, user_id, purpose, expires_at, resend_available_at, attempts,
               locked_until, consumed_at, created_at
        from customer.email_verifications;

        create or replace view public.customer_portal_trusted_devices as
        select id, user_id, label, created_at, last_used_at, expires_at, revoked_at
        from customer.trusted_devices;

        create or replace view public.customer_portal_classifications as
        select id, user_id, predicted_label, confidence, image_name, image_path, created_at
        from customer.classifications;
        """
    )
