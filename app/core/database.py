from functools import lru_cache

from supabase import Client, create_client

from app.core.config import settings


@lru_cache
def get_supabase_client() -> Client:
    """FastAPI dependency — one cached client per process, injected per-request
    instead of a module-level global. Makes services testable with a mock client."""
    return create_client(settings.SUPABASE_URL, settings.SUPABASE_KEY)
