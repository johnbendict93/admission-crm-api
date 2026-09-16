import logging
from datetime import datetime, timezone

from postgrest.exceptions import APIError
from supabase import Client

from app.core.config import settings
from app.models.campus_visits import CampusVisitCreate

logger = logging.getLogger(__name__)

TABLE_NAME = settings.CAMPUS_VISITS_TABLE

# Explicit columns instead of select("*") - matches the real
# campus_visits table exactly, column-by-column (audited via
# information_schema.columns + pg_constraint, Sept 2026).
# deleted_at/deleted_by deliberately excluded from ordinary responses,
# same as every other soft-deleted module.
CAMPUS_VISIT_COLUMNS = "id,lead_id,visit_date,visited_by,departments_seen,outcome,notes,created_at"


def get_all_campus_visits(supabase: Client, limit: int = 50, offset: int = 0):
    try:
        response = (
            supabase.table(TABLE_NAME)
            .select(CAMPUS_VISIT_COLUMNS)
            .is_("deleted_at", "null")  # soft-deleted rows excluded by default
            .order("created_at", desc=True)
            .order("id")  # tiebreaker for stable, deterministic pagination order
            .range(offset, offset + limit - 1)
            .execute()
        )
    except APIError as e:
        logger.error("Supabase error in get_all_campus_visits: %s", e)
        raise
    return response.data


def get_campus_visit_by_id(supabase: Client, campus_visit_id: str):
    try:
        response = (
            supabase.table(TABLE_NAME)
            .select(CAMPUS_VISIT_COLUMNS)
            .eq("id", campus_visit_id)
            .is_("deleted_at", "null")  # soft-deleted rows excluded by default
            .maybe_single()
            .execute()
        )
    except APIError as e:
        logger.error("Supabase error in get_campus_visit_by_id: %s", e)
        raise
    return response.data if response else None


def create_campus_visit(supabase: Client, campus_visit: CampusVisitCreate):
    payload = campus_visit.model_dump(exclude_none=True, mode="json")
    try:
        response = supabase.table(TABLE_NAME).insert(payload).execute()
    except APIError as e:
        logger.error("Supabase error in create_campus_visit: %s", e)
        raise
    return response.data[0] if response.data else None


def update_campus_visit(supabase: Client, campus_visit_id: str, payload: dict):
    try:
        response = (
            supabase.table(TABLE_NAME)
            .update(payload)
            .eq("id", campus_visit_id)
            .execute()
        )
    except APIError as e:
        logger.error("Supabase error in update_campus_visit: %s", e)
        raise
    return response.data[0] if response.data else None


def delete_campus_visit(supabase: Client, campus_visit_id: str, deleted_by: str) -> bool:
    """Soft delete - see leads_service.delete_lead for the full rationale.
    Same double-delete guard: already-deleted or nonexistent both come
    back as zero affected rows, which the router reports as 404."""
    try:
        response = (
            supabase.table(TABLE_NAME)
            .update({"deleted_at": datetime.now(timezone.utc).isoformat(), "deleted_by": deleted_by})
            .eq("id", campus_visit_id)
            .is_("deleted_at", "null")
            .execute()
        )
    except APIError as e:
        logger.error("Supabase error in delete_campus_visit: %s", e)
        raise
    return bool(response.data)
