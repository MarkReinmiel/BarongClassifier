"""Verification rows in private schema, reached through the session pooler."""

from __future__ import annotations

import psycopg

from auth.service import UserRecord
from config import settings


def connect():
    return psycopg.connect(
        host=settings.db_host,
        port=settings.db_port,
        dbname=settings.db_name,
        user=settings.db_user,
        password=settings.db_password,
        sslmode=settings.db_sslmode or "require",
        connect_timeout=15,
    )


class PostgresVerificationStore:
    def issue(self, user_id: str, code_hash: str) -> dict:
        with connect() as connection:
            row = connection.execute(
                "select private.issue_verification_code(%s::uuid, %s)",
                (user_id, code_hash),
            ).fetchone()
        return row[0]

    def consume(self, user_id: str, code_hash: str) -> dict:
        with connect() as connection:
            row = connection.execute(
                "select private.consume_verification_code(%s::uuid, %s)",
                (user_id, code_hash),
            ).fetchone()
        return row[0]

    def save_challenge(self, user_id: str, token_hash: str) -> None:
        with connect() as connection:
            connection.execute(
                "select private.save_challenge(%s::uuid, %s)",
                (user_id, token_hash),
            )

    def take_challenge(self, token_hash: str) -> str | None:
        with connect() as connection:
            row = connection.execute(
                "select private.take_challenge(%s)",
                (token_hash,),
            ).fetchone()
        if not row or not row[0]:
            return None
        return str(row[0])

    def resend_wait_seconds(self, user_id: str) -> int:
        with connect() as connection:
            row = connection.execute(
                """
                select greatest(
                  0,
                  ceil(extract(epoch from (resend_available_at - clock_timestamp())))::int
                )
                from private.email_verifications
                where user_id = %s::uuid
                  and consumed_at is null
                order by created_at desc
                limit 1
                """,
                (user_id,),
            ).fetchone()
        if not row or row[0] is None:
            return 0
        return int(row[0])


def fetch_profile(user_id: str) -> UserRecord:
    with connect() as connection:
        row = connection.execute(
            """
            select id::text, email, full_name, role::text, is_active, email_verified, must_change_password
            from public.profiles
            where id = %s::uuid
            """,
            (user_id,),
        ).fetchone()
    if not row:
        raise LookupError("Profile was not found.")
    return UserRecord(
        id=row[0],
        email=(row[1] or "").lower(),
        full_name=row[2] or "",
        role=row[3] or "customer",
        is_active=bool(row[4]),
        email_verified=bool(row[5]),
        must_change_password=bool(row[6]),
    )


def mark_profile_verified(user_id: str) -> None:
    with connect() as connection:
        connection.execute("select set_config('app.trusted_profile_write', '1', true)")
        connection.execute(
            """
            update public.profiles
            set email_verified = true,
                updated_at = now()
            where id = %s::uuid
            """,
            (user_id,),
        )
