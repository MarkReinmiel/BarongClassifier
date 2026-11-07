from app import create_app
from app.extensions import db
from sqlalchemy import text

app = create_app()
with app.app_context():
    rows = db.session.execute(
        text(
            """
            select table_schema, column_name
            from information_schema.columns
            where table_schema in ('public', 'customer')
              and table_name = 'users'
            order by 1, 2
            """
        )
    ).all()
    for schema, name in rows:
        print(f"{schema}.{name}")
