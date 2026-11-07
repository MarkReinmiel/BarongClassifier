from app import create_app
from app.extensions import db
from app.services.auth_service import _ensure_owner_phone_column
from sqlalchemy import text

app = create_app()
with app.app_context():
    _ensure_owner_phone_column()
    col = db.session.execute(
        text(
            """
            select column_name
            from information_schema.columns
            where table_schema = 'customer'
              and table_name = 'users'
              and column_name = 'phone'
            """
        )
    ).scalar()
    print("phone_column=", col)
