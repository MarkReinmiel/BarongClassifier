"""Retarget public.classifications for Flask portal saves + backfill."""
from __future__ import annotations

from sqlalchemy import text

from app import create_app
from app.extensions import db


SQL = """
-- Allow Flask customer.users ids (not only Supabase Auth users).
alter table public.classifications
  drop constraint if exists classifications_user_id_fkey;

-- Keep user_id as uuid; no FK so Customer/Owner portal accounts can save.
comment on column public.classifications.user_id is
  'Portal or Auth user id. Flask apps write customer.users.id here.';

-- Backfill rows already saved by Flask into customer.classifications.
insert into public.classifications (
  id,
  user_id,
  file_name,
  predicted_label,
  display_name,
  confidence,
  created_at,
  image_path,
  predicted_textile_type,
  confidence_score,
  image_reference
)
select
  c.id::uuid,
  c.user_id::uuid,
  c.image_name,
  c.predicted_label,
  c.predicted_label,
  c.confidence,
  c.created_at,
  c.image_path,
  c.predicted_label,
  c.confidence,
  coalesce(c.image_path, c.image_name)
from customer.classifications c
where c.id ~* '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'
  and c.user_id ~* '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'
on conflict (id) do nothing;
"""


def main() -> None:
    app = create_app()
    with app.app_context():
        db.session.execute(text(SQL))
        db.session.commit()
        public_n = db.session.execute(
            text("select count(*) from public.classifications")
        ).scalar()
        customer_n = db.session.execute(
            text("select count(*) from customer.classifications")
        ).scalar()
        print("ok public_classifications", public_n, "customer_classifications", customer_n)


if __name__ == "__main__":
    main()
