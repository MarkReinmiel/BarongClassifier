"""Create the initial admin only when the Auth user does not already exist.

Passwords are read from the environment and are not printed.
Rerunning this script does not reset an existing password.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from config import settings


def main() -> int:
    if not settings.initial_admin_email:
        print("INITIAL_ADMIN_EMAIL is not set. No account was changed.")
        return 1
    if settings.missing_auth():
        print(
            "Missing configuration: "
            + ", ".join(settings.missing_auth())
            + ". No account was changed."
        )
        return 1

    from auth.supabase_directory import SupabaseDirectory

    directory = SupabaseDirectory()
    existing = (
        directory.admin.table("profiles")
        .select("id, role, is_active, email_verified")
        .eq("email", settings.initial_admin_email)
        .limit(1)
        .execute()
    )
    rows = existing.data or []
    if rows:
        row = rows[0]
        print(
            "Account already exists. Password was not changed. "
            f"role={row.get('role')} active={row.get('is_active')} "
            f"verified={row.get('email_verified')}"
        )
        if row.get("role") == "admin":
            return 0
        if not settings.promote_existing_admin:
            print(
                "Set BOOTSTRAP_PROMOTE_EXISTING_ADMIN=true to grant admin "
                "without changing the password, then run this script again."
            )
            return 2
        directory.set_role(row["id"], "admin")
        print("Existing account was granted the admin role. Password was not changed.")
        return 0

    if not settings.initial_admin_password:
        print("INITIAL_ADMIN_PASSWORD is not set, so a new admin was not created.")
        return 1

    created = directory.admin.auth.admin.create_user(
        {
            "email": settings.initial_admin_email,
            "password": settings.initial_admin_password,
            "email_confirm": True,
            "user_metadata": {"full_name": "BarongClassifier Admin"},
            "app_metadata": {"role": "admin"},
        }
    )
    user = created.user
    if not user:
        print("The Auth API did not return a user. No profile change was confirmed.")
        return 1
    directory.admin.table("profiles").update(
        {
            "role": "admin",
            "email_verified": True,
            "is_active": True,
            "must_change_password": True,
        }
    ).eq("id", user.id).execute()
    print("Administrator account created. A password change is required after the first sign-in.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception:
        print("Administrator bootstrap failed. No password was written to the log.")
        raise SystemExit(1)
