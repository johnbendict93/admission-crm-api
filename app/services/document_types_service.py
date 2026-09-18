import logging

from postgrest.exceptions import APIError
from supabase import Client

from app.core.config import settings
from app.models.document_types import DocumentTypeCreate

logger = logging.getLogger(__name__)

TABLE_NAME = settings.DOCUMENT_TYPES_TABLE

# Explicit columns instead of select("*") - matches the real
# document_types table exactly, column-by-column (audited via
# information_schema.columns + pg_constraint, Sept 2026).
DOCUMENT_TYPE_COLUMNS = "id,name,is_required,sort_order,is_active"

# Judgment call (flagged, not assumed): document_types is a reference/
# config table, not a PII-bearing transactional record like the prior
# seven modules - it has no FKs pointing at it from anywhere else
# (checked prod_schema.sql), and nothing personal in it. Rather than
# add deleted_at/deleted_by (a second "soft removal" mechanism doing
# the same job as the is_active column this table already has), delete
# here just flips is_active to false. Trade-off: no per-action audit of
# who deactivated a row or when - acceptable for admin-managed config
# data. list/get filter to is_active=true, same visible behavior as
# every other module's deleted_at IS NULL filter (a "deleted" row
# disappears from the API but the row itself is never destroyed).


def get_all_document_types(supabase: Client, limit: int = 50, offset: int = 0):
    try:
        response = (
            supabase.table(TABLE_NAME)
            .select(DOCUMENT_TYPE_COLUMNS, count="exact")
            .eq("is_active", True)
            .order("sort_order")
            .order("id")  # tiebreaker for stable, deterministic pagination order
            .range(offset, offset + limit - 1)
            .execute()
        )
    except APIError as e:
        logger.error("Supabase error in get_all_document_types: %s", e)
        raise
    return response.data, response.count


def get_document_type_by_id(supabase: Client, document_type_id: str):
    try:
        response = (
            supabase.table(TABLE_NAME)
            .select(DOCUMENT_TYPE_COLUMNS)
            .eq("id", document_type_id)
            .eq("is_active", True)
            .maybe_single()
            .execute()
        )
    except APIError as e:
        logger.error("Supabase error in get_document_type_by_id: %s", e)
        raise
    return response.data if response else None


def create_document_type(supabase: Client, document_type: DocumentTypeCreate):
    payload = document_type.model_dump(exclude_none=True, mode="json")
    try:
        response = supabase.table(TABLE_NAME).insert(payload).execute()
    except APIError as e:
        logger.error("Supabase error in create_document_type: %s", e)
        raise
    return response.data[0] if response.data else None


def update_document_type(supabase: Client, document_type_id: str, payload: dict):
    try:
        response = (
            supabase.table(TABLE_NAME)
            .update(payload)
            .eq("id", document_type_id)
            .execute()
        )
    except APIError as e:
        logger.error("Supabase error in update_document_type: %s", e)
        raise
    return response.data[0] if response.data else None


def delete_document_type(supabase: Client, document_type_id: str) -> bool:
    """Sets is_active=false rather than hard-deleting - see the module
    docstring above for the reasoning. Same double-delete guard as every
    other module's soft delete: already-inactive or nonexistent both
    come back as zero affected rows, which the router reports as 404."""
    try:
        response = (
            supabase.table(TABLE_NAME)
            .update({"is_active": False})
            .eq("id", document_type_id)
            .eq("is_active", True)
            .execute()
        )
    except APIError as e:
        logger.error("Supabase error in delete_document_type: %s", e)
        raise
    return bool(response.data)
