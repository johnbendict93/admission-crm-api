import logging
from datetime import datetime, timezone

from postgrest.exceptions import APIError
from supabase import Client

from app.core.config import settings
from app.models.applications import ApplicationCreate

logger = logging.getLogger(__name__)

TABLE_NAME = settings.APPLICATIONS_TABLE

# Explicit columns instead of select("*") — matches the real applications
# table exactly, column-by-column (audited via information_schema.columns
# + pg_constraint, Sept 2026).
APPLICATION_COLUMNS = (
    "id,applicant_id,application_no,academic_year,programme,department,"
    "branch,preferred_hostel,preferred_transport,transport_route,"
    "application_stage,merit_rank,allotted_seat_type,remarks,submitted_at,"
    "reviewed_by,reviewed_at,created_at,updated_at,category"
)


def get_all_applications(supabase: Client, limit: int = 50, offset: int = 0):
    try:
        response = (
            supabase.table(TABLE_NAME)
            .select(APPLICATION_COLUMNS)
            .is_("deleted_at", "null")  # soft-deleted rows excluded by default
            .order("created_at", desc=True)
            .order("id")  # tiebreaker: seeded rows share identical created_at,
            # so pagination needs a secondary key for stable, deterministic order
            .range(offset, offset + limit - 1)
            .execute()
        )
    except APIError as e:
        logger.error("Supabase error in get_all_applications: %s", e)
        raise
    return response.data


def get_application_by_id(supabase: Client, application_id: str):
    try:
        response = (
            supabase.table(TABLE_NAME)
            .select(APPLICATION_COLUMNS)
            .eq("id", application_id)
            .is_("deleted_at", "null")  # soft-deleted rows excluded by default
            .maybe_single()
            .execute()
        )
    except APIError as e:
        logger.error("Supabase error in get_application_by_id: %s", e)
        raise
    return response.data if response else None


def create_application(supabase: Client, application: ApplicationCreate):
    payload = application.model_dump(exclude_none=True, mode="json")
    try:
        response = supabase.table(TABLE_NAME).insert(payload).execute()
    except APIError as e:
        logger.error("Supabase error in create_application: %s", e)
        raise
    return response.data[0] if response.data else None


def update_application(supabase: Client, application_id: str, payload: dict):
    try:
        response = (
            supabase.table(TABLE_NAME)
            .update(payload)
            .eq("id", application_id)
            .execute()
        )
    except APIError as e:
        logger.error("Supabase error in update_application: %s", e)
        raise
    return response.data[0] if response.data else None


def delete_application(supabase: Client, application_id: str, deleted_by: str) -> bool:
    """Soft delete - see leads_service.delete_lead for the full rationale.
    Same double-delete guard: already-deleted or nonexistent both come
    back as zero affected rows, which the router reports as 404."""
    try:
        response = (
            supabase.table(TABLE_NAME)
            .update({"deleted_at": datetime.now(timezone.utc).isoformat(), "deleted_by": deleted_by})
            .eq("id", application_id)
            .is_("deleted_at", "null")
            .execute()
        )
    except APIError as e:
        logger.error("Supabase error in delete_application: %s", e)
        raise
    return bool(response.data)
