import logging

from postgrest.exceptions import APIError
from supabase import Client

from app.core.config import settings
from app.models.lookup_values import LookupValueCreate

logger = logging.getLogger(__name__)

TABLE_NAME = settings.LOOKUP_VALUES_TABLE

# Explicit columns instead of select("*") - matches the real
# lookup_values table exactly, column-by-column (audited via
# information_schema.columns + pg_constraint, Sept 2026).
LOOKUP_VALUE_COLUMNS = "id,type,value,sort_order,is_active,created_at"

# Judgment call (flagged, not assumed): same reasoning as
# document_types_service.py - lookup_values is a reference/config table
# with no FKs pointing at it and nothing personal in it, so delete flips
# is_active to false instead of adding a second, redundant
# deleted_at/deleted_by mechanism. list/get filter to is_active=true,
# same visible behavior as every other module's deleted_at IS NULL
# filter.


def get_all_lookup_values(supabase: Client, limit: int = 50, offset: int = 0):
    try:
        response = (
            supabase.table(TABLE_NAME)
            .select(LOOKUP_VALUE_COLUMNS)
            .eq("is_active", True)
            .order("type")
            .order("sort_order")
            .order("id")  # tiebreaker for stable, deterministic pagination order
            .range(offset, offset + limit - 1)
            .execute()
        )
    except APIError as e:
        logger.error("Supabase error in get_all_lookup_values: %s", e)
        raise
    return response.data


def get_lookup_value_by_id(supabase: Client, lookup_value_id: str):
    try:
        response = (
            supabase.table(TABLE_NAME)
            .select(LOOKUP_VALUE_COLUMNS)
            .eq("id", lookup_value_id)
            .eq("is_active", True)
            .maybe_single()
            .execute()
        )
    except APIError as e:
        logger.error("Supabase error in get_lookup_value_by_id: %s", e)
        raise
    return response.data if response else None


def create_lookup_value(supabase: Client, lookup_value: LookupValueCreate):
    payload = lookup_value.model_dump(exclude_none=True, mode="json")
    try:
        response = supabase.table(TABLE_NAME).insert(payload).execute()
    except APIError as e:
        logger.error("Supabase error in create_lookup_value: %s", e)
        raise
    return response.data[0] if response.data else None


def update_lookup_value(supabase: Client, lookup_value_id: str, payload: dict):
    try:
        response = (
            supabase.table(TABLE_NAME)
            .update(payload)
            .eq("id", lookup_value_id)
            .execute()
        )
    except APIError as e:
        logger.error("Supabase error in update_lookup_value: %s", e)
        raise
    return response.data[0] if response.data else None


def delete_lookup_value(supabase: Client, lookup_value_id: str) -> bool:
    """Sets is_active=false rather than hard-deleting - see the module
    docstring above for the reasoning. Same double-delete guard as every
    other module's soft delete: already-inactive or nonexistent both
    come back as zero affected rows, which the router reports as 404."""
    try:
        response = (
            supabase.table(TABLE_NAME)
            .update({"is_active": False})
            .eq("id", lookup_value_id)
            .eq("is_active", True)
            .execute()
        )
    except APIError as e:
        logger.error("Supabase error in delete_lookup_value: %s", e)
        raise
    return bool(response.data)
