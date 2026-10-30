"""Update sync_classification_aliases so bare filenames are not copied into image_path."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "Frontend" / "src" / "owner"))

from app import create_app  # noqa: E402
from app.extensions import db  # noqa: E402
from sqlalchemy import text  # noqa: E402

SQL = r"""
CREATE OR REPLACE FUNCTION public.sync_classification_aliases()
RETURNS trigger
LANGUAGE plpgsql
SET search_path TO 'public'
AS $function$
begin
  if new.predicted_textile_type is null then
    new.predicted_textile_type := new.predicted_label;
  end if;
  if new.predicted_label is null then
    new.predicted_label := new.predicted_textile_type;
  end if;
  if new.confidence_score is null then
    new.confidence_score := new.confidence;
  end if;
  if new.confidence is null then
    new.confidence := new.confidence_score;
  end if;
  -- Only alias URL/path-like values. Never promote a bare filename into image_path.
  if new.image_reference is null
     and new.image_path is not null
     and (new.image_path like 'http%' or position('/' in new.image_path) > 0) then
    new.image_reference := new.image_path;
  end if;
  if new.image_path is null
     and new.image_reference is not null
     and (new.image_reference like 'http%' or position('/' in new.image_reference) > 0) then
    new.image_path := new.image_reference;
  end if;
  return new;
end;
$function$;
"""


def main() -> int:
    app = create_app()
    with app.app_context():
        db.session.execute(text(SQL))
        db.session.commit()
        print("trigger_updated ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
