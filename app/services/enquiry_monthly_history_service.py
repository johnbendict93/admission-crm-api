import logging
from datetime import datetime, timezone

from postgrest.exceptions import APIError
from supabase import Client

from app.core.config import settings
from app.models.enquiry_monthly_history import EnquiryMonthlyHistoryCreate

logger = logging.getLogger(__name__)

TABLE_NAME = settings.ENQUIRY_MONTHLY_HISTORY_TABLE

# Explicit columns instead of select("*") - matches the enquiry_monthly_
# history table exactly, column-by-column (migration 0020). deleted_at/
# deleted_by deliberately excluded from ordinary responses, same as every
# other module in this repo.
ENQUIRY_MONTHLY_HISTORY_COLUMNS = (
    "id,year,month,enquiry_count,source,created_at,updated_at"
)


def get_all_enquiry_monthly_history(supabase: Client, limit: int = 50, offset: int = 0):
    try:
        response = (
            supabase.table(TABLE_NAME)
            .select(ENQUIRY_MONTHLY_HISTORY_COLUMNS, count="exact")
            .is_("deleted_at", "null")  # soft-deleted rows excluded by default
            .order("year")
            .order("month")
            .range(offset, offset + limit - 1)
            .execute()
        )
    except APIError as e:
        logger.error("Supabase error in get_all_enquiry_monthly_history: %s", e)
        raise
    return response.data, response.count


def get_enquiry_monthly_history_by_id(supabase: Client, row_id: str):
    try:
        response = (
            supabase.table(TABLE_NAME)
            .select(ENQUIRY_MONTHLY_HISTORY_COLUMNS)
            .eq("id", row_id)
            .is_("deleted_at", "null")  # soft-deleted rows excluded by default
            .maybe_single()
            .execute()
        )
    except APIError as e:
        logger.error("Supabase error in get_enquiry_monthly_history_by_id: %s", e)
        raise
    return response.data if response else None


def get_all_history_unpaginated(supabase: Client) -> list[dict]:
    """Every non-deleted (year, month, enquiry_count) row, oldest first -
    not paginated, used by module 20's training script which needs the
    whole time series at once, not a page of it. Supabase/PostgREST caps a
    single response at 1000 rows by default; paginated with .range() the
    same way scripts/seed_dev_fake_leads.py's fetch_marked() is, though a
    demand-forecast history table is expected to stay well under that."""
    out, start, page = [], 0, 1000
    while True:
        res = (
            supabase.table(TABLE_NAME)
            .select(ENQUIRY_MONTHLY_HISTORY_COLUMNS)
            .is_("deleted_at", "null")
            .order("year")
            .order("month")
            .range(start, start + page - 1)
            .execute()
        )
        out.extend(res.data)
        if len(res.data) < page:
            break
        start += page
    return out


def create_enquiry_monthly_history(supabase: Client, row: EnquiryMonthlyHistoryCreate):
    payload = row.model_dump(exclude_none=True, mode="json")
    try:
        response = supabase.table(TABLE_NAME).insert(payload).execute()
    except APIError as e:
        logger.error("Supabase error in create_enquiry_monthly_history: %s", e)
        raise
    return response.data[0] if response.data else None


def update_enquiry_monthly_history(supabase: Client, row_id: str, payload: dict):
    try:
        response = (
            supabase.table(TABLE_NAME)
            .update(payload)
            .eq("id", row_id)
            .execute()
        )
    except APIError as e:
        logger.error("Supabase error in update_enquiry_monthly_history: %s", e)
        raise
    return response.data[0] if response.data else None


def delete_enquiry_monthly_history(supabase: Client, row_id: str, deleted_by: str) -> bool:
    """Soft delete - see leads_service.delete_lead for the full rationale.
    Same double-delete guard: already-deleted or nonexistent both come
    back as zero affected rows, which the router reports as 404."""
    try:
        response = (
            supabase.table(TABLE_NAME)
            .update({"deleted_at": datetime.now(timezone.utc).isoformat(), "deleted_by": deleted_by})
            .eq("id", row_id)
            .is_("deleted_at", "null")
            .execute()
        )
    except APIError as e:
        logger.error("Supabase error in delete_enquiry_monthly_history: %s", e)
        raise
    return bool(response.data)
