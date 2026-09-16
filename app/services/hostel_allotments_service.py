import logging
from datetime import datetime, timezone

from postgrest.exceptions import APIError
from supabase import Client

from app.core.config import settings
from app.models.hostel_allotments import HostelAllotmentCreate

logger = logging.getLogger(__name__)

TABLE_NAME = settings.HOSTEL_ALLOTMENTS_TABLE

# Explicit columns instead of select("*") - matches the real
# hostel_allotments table exactly, column-by-column (audited via
# information_schema.columns + pg_constraint, Sept 2026). deleted_at/
# deleted_by deliberately excluded from ordinary responses, same as the
# other five modules.
HOSTEL_ALLOTMENT_COLUMNS = (
    "id,applicant_id,block_name,room_number,room_type,allotment_date,"
    "academic_year,status,remarks,created_at,updated_at"
)


def get_all_hostel_allotments(supabase: Client, limit: int = 50, offset: int = 0):
    try:
        response = (
            supabase.table(TABLE_NAME)
            .select(HOSTEL_ALLOTMENT_COLUMNS)
            .is_("deleted_at", "null")  # soft-deleted rows excluded by default
            .order("created_at", desc=True)
            .order("id")  # tiebreaker for stable, deterministic pagination order
            .range(offset, offset + limit - 1)
            .execute()
        )
    except APIError as e:
        logger.error("Supabase error in get_all_hostel_allotments: %s", e)
        raise
    return response.data


def get_hostel_allotment_by_id(supabase: Client, hostel_allotment_id: str):
    try:
        response = (
            supabase.table(TABLE_NAME)
            .select(HOSTEL_ALLOTMENT_COLUMNS)
            .eq("id", hostel_allotment_id)
            .is_("deleted_at", "null")  # soft-deleted rows excluded by default
            .maybe_single()
            .execute()
        )
    except APIError as e:
        logger.error("Supabase error in get_hostel_allotment_by_id: %s", e)
        raise
    return response.data if response else None


def create_hostel_allotment(supabase: Client, hostel_allotment: HostelAllotmentCreate):
    payload = hostel_allotment.model_dump(exclude_none=True, mode="json")
    try:
        response = supabase.table(TABLE_NAME).insert(payload).execute()
    except APIError as e:
        logger.error("Supabase error in create_hostel_allotment: %s", e)
        raise
    return response.data[0] if response.data else None


def update_hostel_allotment(supabase: Client, hostel_allotment_id: str, payload: dict):
    try:
        response = (
            supabase.table(TABLE_NAME)
            .update(payload)
            .eq("id", hostel_allotment_id)
            .execute()
        )
    except APIError as e:
        logger.error("Supabase error in update_hostel_allotment: %s", e)
        raise
    return response.data[0] if response.data else None


def delete_hostel_allotment(supabase: Client, hostel_allotment_id: str, deleted_by: str) -> bool:
    """Soft delete - see leads_service.delete_lead for the full rationale.
    Same double-delete guard: already-deleted or nonexistent both come
    back as zero affected rows, which the router reports as 404."""
    try:
        response = (
            supabase.table(TABLE_NAME)
            .update({"deleted_at": datetime.now(timezone.utc).isoformat(), "deleted_by": deleted_by})
            .eq("id", hostel_allotment_id)
            .is_("deleted_at", "null")
            .execute()
        )
    except APIError as e:
        logger.error("Supabase error in delete_hostel_allotment: %s", e)
        raise
    return bool(response.data)
