import logging
from datetime import datetime, timezone

from postgrest.exceptions import APIError
from supabase import Client

from app.core.config import settings
from app.models.followups import FollowupCreate

logger = logging.getLogger(__name__)

TABLE_NAME = settings.FOLLOWUPS_TABLE

# Explicit columns instead of select("*") - matches the real followups
# table exactly, column-by-column (audited via information_schema.columns
# + pg_constraint, Sept 2026). deleted_at/deleted_by deliberately
# excluded from ordinary responses, same as every other soft-deleted
# module. Note: this app's own queries always filter deleted_at IS NULL
# (below) - it's only the separate, unmodified Streamlit app that has no
# such filter, per the prod-safety note in migrations/0010.
FOLLOWUP_COLUMNS = "id,lead_id,called_by,call_date,call_time,response,notes,next_followup_date,created_at"


def get_all_followups(supabase: Client, limit: int = 50, offset: int = 0):
    try:
        response = (
            supabase.table(TABLE_NAME)
            .select(FOLLOWUP_COLUMNS)
            .is_("deleted_at", "null")  # soft-deleted rows excluded by default
            .order("created_at", desc=True)
            .order("id")  # tiebreaker for stable, deterministic pagination order
            .range(offset, offset + limit - 1)
            .execute()
        )
    except APIError as e:
        logger.error("Supabase error in get_all_followups: %s", e)
        raise
    return response.data


def get_followup_by_id(supabase: Client, followup_id: str):
    try:
        response = (
            supabase.table(TABLE_NAME)
            .select(FOLLOWUP_COLUMNS)
            .eq("id", followup_id)
            .is_("deleted_at", "null")  # soft-deleted rows excluded by default
            .maybe_single()
            .execute()
        )
    except APIError as e:
        logger.error("Supabase error in get_followup_by_id: %s", e)
        raise
    return response.data if response else None


def create_followup(supabase: Client, followup: FollowupCreate):
    payload = followup.model_dump(exclude_none=True, mode="json")
    try:
        response = supabase.table(TABLE_NAME).insert(payload).execute()
    except APIError as e:
        logger.error("Supabase error in create_followup: %s", e)
        raise
    return response.data[0] if response.data else None


def update_followup(supabase: Client, followup_id: str, payload: dict):
    try:
        response = (
            supabase.table(TABLE_NAME)
            .update(payload)
            .eq("id", followup_id)
            .execute()
        )
    except APIError as e:
        logger.error("Supabase error in update_followup: %s", e)
        raise
    return response.data[0] if response.data else None


def delete_followup(supabase: Client, followup_id: str, deleted_by: str) -> bool:
    """Soft delete - see leads_service.delete_lead for the full rationale.
    Same double-delete guard: already-deleted or nonexistent both come
    back as zero affected rows, which the router reports as 404."""
    try:
        response = (
            supabase.table(TABLE_NAME)
            .update({"deleted_at": datetime.now(timezone.utc).isoformat(), "deleted_by": deleted_by})
            .eq("id", followup_id)
            .is_("deleted_at", "null")
            .execute()
        )
    except APIError as e:
        logger.error("Supabase error in delete_followup: %s", e)
        raise
    return bool(response.data)
