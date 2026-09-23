import logging
from datetime import datetime, timezone

from postgrest.exceptions import APIError
from supabase import Client

from app.core.config import settings
from app.models.fee_due_schedule import FeeDueScheduleCreate

logger = logging.getLogger(__name__)

TABLE_NAME = settings.FEE_DUE_SCHEDULE_TABLE

# Explicit columns instead of select("*") - matches the fee_due_schedule
# table exactly, column-by-column (migration 0019). deleted_at/deleted_by
# deliberately excluded from ordinary responses, same as fee_payments/
# leads/applicants/applications.
FEE_DUE_SCHEDULE_COLUMNS = (
    "id,applicant_id,fee_component,academic_year,amount_due,due_date,created_at,updated_at"
)


def get_all_fee_due_schedules(supabase: Client, limit: int = 50, offset: int = 0):
    try:
        response = (
            supabase.table(TABLE_NAME)
            .select(FEE_DUE_SCHEDULE_COLUMNS, count="exact")
            .is_("deleted_at", "null")  # soft-deleted rows excluded by default
            .order("due_date")
            .order("id")  # tiebreaker for stable, deterministic pagination order
            .range(offset, offset + limit - 1)
            .execute()
        )
    except APIError as e:
        logger.error("Supabase error in get_all_fee_due_schedules: %s", e)
        raise
    return response.data, response.count


def get_fee_due_schedule_by_id(supabase: Client, fee_due_schedule_id: str):
    try:
        response = (
            supabase.table(TABLE_NAME)
            .select(FEE_DUE_SCHEDULE_COLUMNS)
            .eq("id", fee_due_schedule_id)
            .is_("deleted_at", "null")  # soft-deleted rows excluded by default
            .maybe_single()
            .execute()
        )
    except APIError as e:
        logger.error("Supabase error in get_fee_due_schedule_by_id: %s", e)
        raise
    return response.data if response else None


def get_due_schedules_for_applicant(supabase: Client, applicant_id: str):
    """All non-deleted due rows for one applicant, earliest due date first -
    not paginated, used by module 18's feature builder which needs the
    applicant's whole schedule at once, not a page of it."""
    try:
        response = (
            supabase.table(TABLE_NAME)
            .select(FEE_DUE_SCHEDULE_COLUMNS)
            .eq("applicant_id", applicant_id)
            .is_("deleted_at", "null")
            .order("due_date")
            .execute()
        )
    except APIError as e:
        logger.error("Supabase error in get_due_schedules_for_applicant: %s", e)
        raise
    return response.data


def create_fee_due_schedule(supabase: Client, fee_due_schedule: FeeDueScheduleCreate):
    payload = fee_due_schedule.model_dump(exclude_none=True, mode="json")
    try:
        response = supabase.table(TABLE_NAME).insert(payload).execute()
    except APIError as e:
        logger.error("Supabase error in create_fee_due_schedule: %s", e)
        raise
    return response.data[0] if response.data else None


def update_fee_due_schedule(supabase: Client, fee_due_schedule_id: str, payload: dict):
    try:
        response = (
            supabase.table(TABLE_NAME)
            .update(payload)
            .eq("id", fee_due_schedule_id)
            .execute()
        )
    except APIError as e:
        logger.error("Supabase error in update_fee_due_schedule: %s", e)
        raise
    return response.data[0] if response.data else None


def delete_fee_due_schedule(supabase: Client, fee_due_schedule_id: str, deleted_by: str) -> bool:
    """Soft delete - see leads_service.delete_lead for the full rationale.
    Same double-delete guard: already-deleted or nonexistent both come
    back as zero affected rows, which the router reports as 404."""
    try:
        response = (
            supabase.table(TABLE_NAME)
            .update({"deleted_at": datetime.now(timezone.utc).isoformat(), "deleted_by": deleted_by})
            .eq("id", fee_due_schedule_id)
            .is_("deleted_at", "null")
            .execute()
        )
    except APIError as e:
        logger.error("Supabase error in delete_fee_due_schedule: %s", e)
        raise
    return bool(response.data)
