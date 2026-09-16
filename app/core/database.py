from functools import lru_cache

from supabase import Client, create_client

from app.core.config import settings


@lru_cache
def get_supabase_client() -> Client:
    """FastAPI dependency — one cached client per process, injected per-request
    instead of a module-level global. Makes services testable with a mock client.

    Uses the service_role key: full CRUD access, bypasses RLS. This is the
    client every business router and service uses."""
    return create_client(settings.SUPABASE_URL, settings.SUPABASE_KEY)


@lru_cache
def get_supabase_auth_client() -> Client:
    """A separate client instantiated with the anon (public) key, used only
    for the login endpoint's sign_in_with_password() call (app/routers/auth.py).
    The anon key is the correct, minimal-privilege credential for a
    client-facing auth operation — the service_role key above must never be
    used to authenticate an end user."""
    return create_client(settings.SUPABASE_URL, settings.SUPABASE_ANON_KEY)
