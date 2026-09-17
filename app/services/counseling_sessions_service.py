import logging
from datetime import datetime, timezone

from postgrest.exceptions import APIError
from supabase import Client

from app.core.config import settings
from app.models.counseling_sessions import CounselingSessionCreate

logger = logging.getLogger(__name__)

TABLE_NAME = settings.COUNSELING_SESSIONS_TABLE

# Explicit columns instead of select("*") - matches the real
# counseling_sessions table exactly, column-by-column (audited via
# information_schema.columns + pg_constraint + pg_trigger, Sept 2026).
# deleted_at/deleted_by deliberately excluded from ordinary responses,
# same as every other soft-deleted module.
COUNSELING_SESSION_COLUMNS = (
    "id,applicant_id,application_id,counselor_id,session_type,session_date,"
    "duration_mins,topics_discussed,outcome,next_action,next_action_date,"
    "notes,mode,created_at,updated_at"
)


def get_all_counseling_sessions(supabase: Client, limit: int = 50, offset: int = 0):
    try:
        response = (
            supabase.table(TABLE_NAME)
            .select(COUNSELING_SESSION_COLUMNS)
            .is_("deleted_at", "null")  # soft-deleted rows excluded by default
            .order("created_at", desc=True)
            .order("id")  # tiebreaker for stable, deterministic pagination order
            .range(offset, offset + limit - 1)
            .execute()
        )
    except APIError as e:
        logger.error("Supabase error in get_all_counseling_sessions: %s", e)
        raise
    return response.data


def get_counseling_session_by_id(supabase: Client, counseling_session_id: str):
    try:
        response = (
            supabase.table(TABLE_NAME)
            .select(COUNSELING_SESSION_COLUMNS)
            .eq("id", counseling_session_id)
            .is_("deleted_at", "null")  # soft-deleted rows excluded by default
            .maybe_single()
            .execute()
        )
    except APIError as e:
        logger.error("Supabase error in get_counseling_session_by_id: %s", e)
        raise
    return response.data if response else None


def create_counseling_session(supabase: Client, counseling_session: CounselingSessionCreate):
    payload = counseling_session.model_dump(exclude_none=True, mode="json")
    try:
        response = supabase.table(TABLE_NAME).insert(payload).execute()
    except APIError as e:
        logger.error("Supabase error in create_counseling_session: %s", e)
        raise
    return response.data[0] if response.data else None


def update_counseling_session(supabase: Client, counseling_session_id: str, payload: dict):
    try:
        response = (
            supabase.table(TABLE_NAME)
            .update(payload)
            .eq("id", counseling_session_id)
            .execute()
        )
    except APIError as e:
        logger.error("Supabase error in update_counseling_session: %s", e)
        raise
    return response.data[0] if response.data else None


def delete_counseling_session(supabase: Client, counseling_session_id: str, deleted_by: str) -> bool:
    """Soft delete - see leads_service.delete_lead for the full rationale.
    Same double-delete guard: already-deleted or nonexistent both come
    back as zero affected rows, which the router reports as 404."""
    try:
        response = (
            supabase.table(TABLE_NAME)
            .update({"deleted_at": datetime.now(timezone.utc).isoformat(), "deleted_by": deleted_by})
            .eq("id", counseling_session_id)
            .is_("deleted_at", "null")
            .execute()
        )
    except APIError as e:
        logger.error("Supabase error in delete_counseling_session: %s", e)
        raise
    return bool(response.data)
