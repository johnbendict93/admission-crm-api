#!/usr/bin/env python3
"""
One-time setup script: creates the two dedicated test accounts the pytest
suite needs in order to authenticate with real JWTs (see tests/conftest.py -
admin_access_token / viewer_access_token fixtures) - one with an
admin-level role (to exercise DELETE, which only admin/staff may do) and
one with the viewer role (to exercise the read-only restriction).

Run this ONCE against dev:
    python scripts/create_test_users.py

It is idempotent - safe to re-run. If a test account's email already
exists in Supabase Auth, it is left alone (not recreated, password not
changed); only its public.users role is (re-)corrected if it drifted.

After it creates a brand-new account, it prints the generated email and
password ONCE - copy those into .env as TEST_ADMIN_EMAIL/TEST_ADMIN_PASSWORD
and TEST_VIEWER_EMAIL/TEST_VIEWER_PASSWORD. This script never writes to
.env itself and never hardcodes real credentials anywhere else in the
repo - those four .env values are the only place they persist.

Uses the service_role key's Admin API (auth.admin.create_user), so it must
run against dev only - the same ENVIRONMENT=development / SUPABASE_URL
guard the pytest suite itself uses (tests/conftest.py) is checked here too
before doing anything.
"""
import secrets
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.config import settings  # noqa: E402
from app.core.database import get_supabase_client  # noqa: E402

TEST_ACCOUNTS = [
    {
        "role": "admin",
        "default_email": "test-admin@admission-crm.test",
        "configured_email": settings.TEST_ADMIN_EMAIL,
        "env_email_var": "TEST_ADMIN_EMAIL",
        "env_password_var": "TEST_ADMIN_PASSWORD",
    },
    {
        "role": "viewer",
        "default_email": "test-viewer@admission-crm.test",
        "configured_email": settings.TEST_VIEWER_EMAIL,
        "env_email_var": "TEST_VIEWER_EMAIL",
        "env_password_var": "TEST_VIEWER_PASSWORD",
    },
]


def main():
    if settings.ENVIRONMENT != "development":
        sys.exit(
            f"Refusing to run: ENVIRONMENT={settings.ENVIRONMENT!r}, not "
            "'development'. This script creates real Supabase Auth users "
            "and must never run against production."
        )
    if settings.SUPABASE_URL == settings.PROD_SUPABASE_URL:
        sys.exit(
            "Refusing to run: the active SUPABASE_URL matches "
            "PROD_SUPABASE_URL. DEV_SUPABASE_URL is likely misconfigured."
        )

    supabase = get_supabase_client()
    existing_users = {u.email: u for u in supabase.auth.admin.list_users(per_page=1000)}

    for account in TEST_ACCOUNTS:
        email = account["configured_email"] or account["default_email"]

        if email in existing_users:
            user_id = existing_users[email].id
            print(f"[{account['role']}] {email} already exists (id={user_id}) - leaving credentials as-is.")
        else:
            password = secrets.token_urlsafe(18)
            created = supabase.auth.admin.create_user(
                {
                    "email": email,
                    "password": password,
                    "email_confirm": True,  # skip email verification - synthetic test account
                }
            )
            user_id = created.user.id
            print(f"[{account['role']}] Created {email} (id={user_id}).")
            print("  Add to .env:")
            print(f"    {account['env_email_var']}={email}")
            print(f"    {account['env_password_var']}={password}")

        # handle_new_auth_user() defaults every new signup to role='counselor'
        # (see migrations/0001_initial_schema.sql) - correct it here to the
        # role this test account actually needs to exercise.
        supabase.table(settings.USERS_TABLE).update({"role": account["role"]}).eq("id", user_id).execute()
        print(f"  Role set to '{account['role']}' in {settings.USERS_TABLE}.")


if __name__ == "__main__":
    main()
