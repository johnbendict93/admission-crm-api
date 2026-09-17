import logging

from postgrest.exceptions import APIError
from supabase import Client

from app.core.config import settings as app_settings
from app.models.settings import SettingCreate

logger = logging.getLogger(__name__)

TABLE_NAME = app_settings.SETTINGS_TABLE

# Explicit columns instead of select("*") - matches the real settings
# table exactly, column-by-column (audited via information_schema.columns
# + pg_constraint, Sept 2026).
SETTING_COLUMNS = "id,category,key,value,is_active,created_at,updated_at"

# Judgment call (flagged, not assumed): settings is a reference/config
# table, not a transactional record tied to a business entity like
# leads - it has no FKs pointing at it from anywhere else (checked
# prod_schema.sql), and nothing personal in it. Rather than add
# deleted_at/deleted_by (a second "soft removal" mechanism doing the
# same job as the is_active column this table already has), delete here
# just flips is_active to false - same pattern as document_types/
# lookup_values. Trade-off: no per-action audit of who deactivated a row
# or when - acceptable for admin-managed config data. list/get filter to
# is_active=true, same visible behavior as every other module's
# deleted_at IS NULL filter.


def get_all_settings(supabase: Client, limit: int = 50, offset: int = 0):
    try:
        response = (
            supabase.table(TABLE_NAME)
            .select(SETTING_COLUMNS)
            .eq("is_active", True)
            .order("category")
            .order("key")
            .range(offset, offset + limit - 1)
            .execute()
        )
    except APIError as e:
        logger.error("Supabase error in get_all_settings: %s", e)
        raise
    return response.data


def get_setting_by_id(supabase: Client, setting_id: str):
    try:
        response = (
            supabase.table(TABLE_NAME)
            .select(SETTING_COLUMNS)
            .eq("id", setting_id)
            .eq("is_active", True)
            .maybe_single()
            .execute()
        )
    except APIError as e:
        logger.error("Supabase error in get_setting_by_id: %s", e)
        raise
    return response.data if response else None


def create_setting(supabase: Client, setting: SettingCreate):
    payload = setting.model_dump(exclude_none=True, mode="json")
    try:
        response = supabase.table(TABLE_NAME).insert(payload).execute()
    except APIError as e:
        logger.error("Supabase error in create_setting: %s", e)
        raise
    return response.data[0] if response.data else None


def update_setting(supabase: Client, setting_id: str, payload: dict):
    try:
        response = (
            supabase.table(TABLE_NAME)
            .update(payload)
            .eq("id", setting_id)
            .execute()
        )
    except APIError as e:
        logger.error("Supabase error in update_setting: %s", e)
        raise
    return response.data[0] if response.data else None


def delete_setting(supabase: Client, setting_id: str) -> bool:
    """Sets is_active=false rather than hard-deleting - see the module
    docstring above for the reasoning. Same double-delete guard as every
    other is_active-based module: already-inactive or nonexistent both
    come back as zero affected rows, which the router reports as 404."""
    try:
        response = (
            supabase.table(TABLE_NAME)
            .update({"is_active": False})
            .eq("id", setting_id)
            .eq("is_active", True)
            .execute()
        )
    except APIError as e:
        logger.error("Supabase error in delete_setting: %s", e)
        raise
    return bool(response.data)
