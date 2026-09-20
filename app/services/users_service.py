import logging
from typing import Iterable, List, Optional

from postgrest.exceptions import APIError
from supabase import Client
from supabase_auth.errors import AuthApiError

from app.core.config import settings as app_settings

logger = logging.getLogger(__name__)

TABLE_NAME = app_settings.USERS_TABLE

# Explicit, minimal column list - NOT select("*"). This is the privacy
# boundary of the whole module: email, phone and avatar_url are never
# requested from the database, so they can never appear in a response.
# Confirmed against the live public.users columns on dev and prod
# (Sept 2026 identity audit).
USER_COLUMNS = "id,full_name,role,department,is_active"

# Users are provisioned by Supabase Auth through the on_auth_user_created
# trigger (migration 0002); create_user() below drives that trigger and then
# fixes up the row. public.users has no deleted_at/deleted_by - is_active is its own
# soft-removal flag. list/get therefore filter to is_active = true, the
# same visible behavior as the other is_active-based modules
# (settings/document_types/lookup_values).


def normalize_roles(values: Optional[Iterable[str]]) -> Optional[List[str]]:
    """Accepts the ?role= query values in either style - repeated
    (?role=admin&role=staff) or comma-separated (?role=admin,staff), or a
    mix - and returns a de-duplicated, order-preserving list, or None when
    nothing usable was supplied (meaning: do not filter by role at all).

    Deliberately does NOT validate against a hardcoded role list: the DB's
    users_role_check CHECK constraint owns the allowed values, and an
    unknown role simply matches no rows.
    """
    if not values:
        return None
    seen = []
    for raw in values:
        for part in raw.split(","):
            role = part.strip()
            if role and role not in seen:
                seen.append(role)
    return seen or None


def get_all_users(supabase: Client, roles: Optional[List[str]] = None, limit: int = 50, offset: int = 0):
    try:
        query = supabase.table(TABLE_NAME).select(USER_COLUMNS, count="exact").eq("is_active", True)
        if roles:
            query = query.in_("role", roles)
        # id as a tiebreaker keeps pagination stable when names collide.
        response = query.order("full_name").order("id").range(offset, offset + limit - 1).execute()
    except APIError as e:
        logger.error("Supabase error in get_all_users: %s", e)
        raise
    return response.data, response.count


def get_user_by_id(supabase: Client, user_id: str):
    try:
        response = (
            supabase.table(TABLE_NAME)
            .select(USER_COLUMNS)
            .eq("id", user_id)
            .eq("is_active", True)
            .maybe_single()
            .execute()
        )
    except APIError as e:
        logger.error("Supabase error in get_user_by_id: %s", e)
        raise
    return response.data if response else None


class EmailAlreadyExists(Exception):
    """A Supabase Auth account with this email already exists."""


def create_user(supabase: Client, data) -> dict:
    """Creates a login in Supabase Auth (service-role client), lets the
    on_auth_user_created trigger create the public.users row (always as
    'counselor'), then sets the role/department/name the admin chose.

    If anything fails after the login was created, the login is deleted
    again so no orphan account (login without a users row) is left behind.
    Raises EmailAlreadyExists for a duplicate email; AuthApiError / APIError
    propagate for anything else. The password is never logged.
    """
    try:
        created = supabase.auth.admin.create_user(
            {
                "email": str(data.email),
                "password": data.temporary_password,
                "email_confirm": True,
                "user_metadata": {"full_name": data.full_name},
            }
        )
    except AuthApiError as e:
        if getattr(e, "code", None) == "email_exists":
            raise EmailAlreadyExists() from e
        logger.error("Supabase Auth error in create_user: %s", getattr(e, "message", e))
        raise

    user_id = created.user.id
    try:
        updated = (
            supabase.table(TABLE_NAME)
            .update({"role": data.role, "department": data.department, "full_name": data.full_name})
            .eq("id", user_id)
            .execute()
        )
        if not updated.data:
            raise RuntimeError("users row was not created by the auth trigger")
        return (
            supabase.table(TABLE_NAME).select(USER_COLUMNS).eq("id", user_id).single().execute()
        ).data
    except Exception:
        logger.error("create_user failed after login was created; rolling back the login")
        try:
            supabase.auth.admin.delete_user(user_id)
        except Exception:
            logger.exception("Rollback failed: orphan auth user %s needs manual cleanup", user_id)
        raise
